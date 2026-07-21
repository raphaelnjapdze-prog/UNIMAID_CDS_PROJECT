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
    @staticmethod
    def _seed(monkeypatch, entries):
        """Isolate the queue from the cookie and load it with the given entries."""
        import streamlit as st
        st.session_state.clear()
        monkeypatch.setattr(oq, "read_pending_queue", lambda: None)
        monkeypatch.setattr(oq, "write_pending_queue", lambda v: None)
        st.session_state[oq._QUEUE_STATE_KEY] = list(entries)
        st.session_state[oq._HYDRATED_KEY] = True
        return st

    def test_successful_syncs_are_removed_and_counted(self, monkeypatch):
        st = self._seed(monkeypatch, [_entry(1), _entry(2)])

        assert oq.drain(lambda kind, payload: oq.SYNC_OK) == (2, 0, 0)
        st.session_state.clear()

    def test_a_transient_failure_stops_the_drain_and_keeps_the_rest(self, monkeypatch):
        st = self._seed(monkeypatch, [_entry(1), _entry(2), _entry(3)])

        # First entry syncs, second is offline — third must stay queued too, and
        # nothing that didn't confirm may be dropped.
        calls = {"n": 0}

        def flaky(kind, payload):
            calls["n"] += 1
            return oq.SYNC_OK if calls["n"] == 1 else oq.SYNC_RETRY

        assert oq.drain(flaky) == (1, 2, 0)
        st.session_state.clear()

    def test_a_raising_sync_leaves_entry_queued(self, monkeypatch):
        st = self._seed(monkeypatch, [_entry(1)])

        def boom(kind, payload):
            raise ConnectionError("offline")

        assert oq.drain(boom) == (0, 1, 0)
        st.session_state.clear()


class TestRejectedEntriesDoNotWedgeTheQueue:
    """A permanently-rejected entry must not block the entries behind it.

    Entries are queued only after a *network* failure, so the payload was never
    server-validated — schema drift can surface as a hard rejection at drain time.
    Treating that as 'still offline' would park it at the head of the queue forever
    and stall every later collection behind it.
    """

    def test_a_rejected_entry_is_quarantined_and_the_rest_still_sync(self, monkeypatch):
        st = TestDrain._seed(monkeypatch, [_entry(1), _entry(2), _entry(3)])

        def reject_first(kind, payload):
            if payload["specimen_id"] == "id-1":
                return oq.SYNC_REJECTED, "column does not exist"
            return oq.SYNC_OK

        synced, remaining, rejected = oq.drain(reject_first)

        assert (synced, remaining, rejected) == (2, 0, 1)
        # Quarantined, not discarded: the payload is still recoverable by the UI.
        quarantine = oq.get_quarantine()
        assert len(quarantine) == 1
        assert quarantine[0]["payload"]["specimen_id"] == "id-1"
        assert quarantine[0]["error"] == "column does not exist"
        st.session_state.clear()

    def test_a_rejected_entry_does_not_come_back_on_the_next_drain(self, monkeypatch):
        st = TestDrain._seed(monkeypatch, [_entry(1)])
        oq.drain(lambda kind, payload: (oq.SYNC_REJECTED, "bad schema"))

        # Second drain has nothing left to do — the entry is not retried forever.
        assert oq.drain(lambda kind, payload: oq.SYNC_OK) == (0, 0, 0)
        assert len(oq.get_quarantine()) == 1
        st.session_state.clear()

    def test_transient_failure_never_quarantines(self, monkeypatch):
        st = TestDrain._seed(monkeypatch, [_entry(1)])

        assert oq.drain(lambda kind, payload: oq.SYNC_RETRY) == (0, 1, 0)
        assert oq.get_quarantine() == []
        st.session_state.clear()

    def test_clear_quarantine_empties_it(self, monkeypatch):
        st = TestDrain._seed(monkeypatch, [_entry(1)])
        oq.drain(lambda kind, payload: (oq.SYNC_REJECTED, "nope"))
        assert len(oq.get_quarantine()) == 1

        oq.clear_quarantine()

        assert oq.get_quarantine() == []
        st.session_state.clear()
