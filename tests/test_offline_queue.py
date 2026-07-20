"""The offline queue must never lose or silently drop a field entry.

Streamlit can't run with zero signal, but a transient Supabase/DNS drop or a reload
must not cost a field worker the collection they just typed. These pin the pure queue
logic: round-trip encoding, the cap that keeps the queue inside one cookie, and a
drain that only removes entries that actually synced.
"""
import utils.offline_queue as oq


def _entry(n: int) -> dict:
    return oq.make_entry("site_log", {"specimen_id": f"id-{n}", "anopheles_count": n})


class TestEncodeRoundTrip:
    def test_encode_then_decode_is_identity(self):
        queue = [_entry(1), _entry(2)]
        assert oq.decode_queue(oq.encode_queue(queue)) == queue

    def test_encoded_value_is_cookie_safe(self):
        # No character a cookie value forbids (';', ',', whitespace, quotes, backslash).
        encoded = oq.encode_queue([_entry(i) for i in range(3)])
        assert not any(c in encoded for c in '; ,"\\\t\n')

    def test_corrupt_value_decodes_to_empty_not_crash(self):
        assert oq.decode_queue("not-valid-base64!!") == []
        assert oq.decode_queue(None) == []
        assert oq.decode_queue("") == []


class TestCap:
    def test_add_refuses_past_the_entry_cap(self):
        queue = []
        for i in range(oq.MAX_PENDING):
            queue, ok = oq.add_entry(queue, _entry(i))
            assert ok
        queue, ok = oq.add_entry(queue, _entry(99))
        assert ok is False
        assert len(queue) == oq.MAX_PENDING  # unchanged; nothing dropped

    def test_full_queue_reports_full(self):
        queue = [_entry(i) for i in range(oq.MAX_PENDING)]
        assert oq.queue_is_full(queue) is True


class TestRemove:
    def test_remove_targets_only_the_given_id(self):
        a, b = _entry(1), _entry(2)
        assert oq.remove_entry([a, b], a["id"]) == [b]

    def test_remove_unknown_id_is_a_noop(self):
        a = _entry(1)
        assert oq.remove_entry([a], "nope") == [a]


class TestDrain:
    def test_successful_syncs_are_removed_and_counted(self, monkeypatch):
        import streamlit as st
        st.session_state.clear()
        monkeypatch.setattr(oq, "read_pending_queue", lambda: None)
        monkeypatch.setattr(oq, "write_pending_queue", lambda v: None)
        st.session_state[oq._QUEUE_STATE_KEY] = [_entry(1), _entry(2)]
        st.session_state[oq._HYDRATED_KEY] = True

        synced, remaining = oq.drain(lambda kind, payload: True)

        assert (synced, remaining) == (2, 0)
        st.session_state.clear()

    def test_a_failed_sync_stops_the_drain_and_keeps_the_rest(self, monkeypatch):
        import streamlit as st
        st.session_state.clear()
        monkeypatch.setattr(oq, "read_pending_queue", lambda: None)
        monkeypatch.setattr(oq, "write_pending_queue", lambda v: None)
        st.session_state[oq._QUEUE_STATE_KEY] = [_entry(1), _entry(2), _entry(3)]
        st.session_state[oq._HYDRATED_KEY] = True

        # First entry syncs, second fails (still offline) — third must stay queued too,
        # and nothing that didn't confirm may be dropped.
        calls = {"n": 0}

        def flaky(kind, payload):
            calls["n"] += 1
            return calls["n"] == 1

        synced, remaining = oq.drain(flaky)

        assert (synced, remaining) == (1, 2)
        st.session_state.clear()

    def test_a_raising_sync_leaves_entry_queued(self, monkeypatch):
        import streamlit as st
        st.session_state.clear()
        monkeypatch.setattr(oq, "read_pending_queue", lambda: None)
        monkeypatch.setattr(oq, "write_pending_queue", lambda v: None)
        st.session_state[oq._QUEUE_STATE_KEY] = [_entry(1)]
        st.session_state[oq._HYDRATED_KEY] = True

        def boom(kind, payload):
            raise ConnectionError("offline")

        synced, remaining = oq.drain(boom)

        assert (synced, remaining) == (0, 1)
        st.session_state.clear()
