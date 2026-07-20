"""Durable pending-write queue for field entries, so a network blip or a reload
never silently loses a collection.

Streamlit runs the app server-side over a live connection, so a phone with NO
signal cannot run the app at all — this module does NOT make the app work fully
offline (see CLAUDE.md's note on the SPA model). What it covers is the failure
that actually bites in the field:

  * a save that fails because Supabase (or DNS) is momentarily unreachable while
    the Streamlit server is still up — exactly the `getaddrinfo` drop we hit; and
  * a reload / Streamlit-Cloud idle-reboot mid-shift, which wipes st.session_state.

A failed site-log save is parked in a queue that lives in st.session_state (fast
and reliable within a session) and is mirrored into a browser cookie — the same
cross-reload mechanism the Supabase refresh token already uses — so it survives a
full reload. The queue is drained back to Supabase on the next successful
connection or when the user taps "Sync now".

Honest limits, enforced here rather than hidden:
  * Text only. A photo needs a live upload, so an offline entry is queued without
    its photo; it can be attached later once online.
  * Small and capped. A cookie holds ~4 KB, so the queue caps at MAX_PENDING
    entries (and a byte budget); past that, new offline entries are refused until
    the backlog syncs. Sized for intermittent connectivity, not a long backlog.

The pure functions below (make_entry / add_entry / remove_entry / encode / decode
/ queue_is_full) hold no Streamlit or network state and are unit-tested. The
stateful glue (get_queue / persist_queue / enqueue_site_log / drain) wires them to
st.session_state and the cookie.
"""

import base64
import json
import uuid
from datetime import datetime, timezone

import streamlit as st

from utils.logging_config import get_logger
from utils.session_cookie import read_pending_queue, write_pending_queue

logger = get_logger(__name__)

# One session-state key holds the live queue; the cookie mirrors it for reloads.
_QUEUE_STATE_KEY = "offline_pending_queue"
# Set once per session after we've read the cookie, so a reload hydrates the queue
# exactly once rather than clobbering in-session additions on every rerun.
_HYDRATED_KEY = "offline_queue_hydrated"

# Kept deliberately small: the whole queue must fit in one ~4 KB cookie. A field
# log payload is a few hundred bytes, so a handful is the safe ceiling.
MAX_PENDING = 6
# Encoded (base64) budget, well under the ~4 KB cookie limit to leave room for the
# cookie's own attributes. add_entry refuses an addition that would exceed this.
_MAX_ENCODED_BYTES = 3600


# ---------------------------------------------------------------------------
# Pure queue logic (no Streamlit, no network) — unit-tested.
# ---------------------------------------------------------------------------
def make_entry(kind: str, payload: dict) -> dict:
    """Wrap a write payload in a queue entry with a stable id and a queued-at stamp.

    The id lets the UI address one entry (to drop it after a successful sync) and
    is independent of any id inside the payload.
    """
    return {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "payload": payload,
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }


def queue_is_full(queue: list, max_pending: int = MAX_PENDING) -> bool:
    """True if the queue has reached the entry cap."""
    return len(queue) >= max_pending


def add_entry(queue: list, entry: dict, max_pending: int = MAX_PENDING) -> tuple[list, bool]:
    """Return (new_queue, accepted). Refuses the add — leaving the queue unchanged —
    if it would exceed either the entry cap or the encoded byte budget, so we never
    build a queue that can't be persisted to the cookie."""
    if queue_is_full(queue, max_pending):
        return queue, False
    candidate = [*queue, entry]
    if len(encode_queue(candidate).encode("utf-8")) > _MAX_ENCODED_BYTES:
        return queue, False
    return candidate, True


def remove_entry(queue: list, entry_id: str) -> list:
    """Return a copy of the queue with the entry of the given id removed."""
    return [e for e in queue if e.get("id") != entry_id]


def encode_queue(queue: list) -> str:
    """Serialize the queue to a cookie-safe string (base64url of JSON, no padding).

    base64url avoids every character a cookie value forbids (`;`, `,`, whitespace,
    quotes, backslash); padding `=` is stripped and restored on decode.
    """
    raw = json.dumps(queue, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_queue(value: str | None) -> list:
    """Inverse of encode_queue. Returns [] for anything unparseable rather than
    raising — a corrupt cookie must degrade to an empty queue, never crash entry."""
    if not value:
        return []
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        return data if isinstance(data, list) else []
    except Exception:
        logger.debug("Could not decode pending-queue cookie; treating as empty", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Stateful glue: session_state + cookie mirror.
# ---------------------------------------------------------------------------
def get_queue() -> list:
    """The live pending queue, hydrated once per session from the cookie.

    Within a session the source of truth is st.session_state (a reload starts a new
    session with empty state, which is when we read the cookie back in).
    """
    if not st.session_state.get(_HYDRATED_KEY):
        if _QUEUE_STATE_KEY not in st.session_state:
            st.session_state[_QUEUE_STATE_KEY] = decode_queue(read_pending_queue())
        st.session_state[_HYDRATED_KEY] = True
    return st.session_state.get(_QUEUE_STATE_KEY, [])


def persist_queue(queue: list) -> None:
    """Write the queue to both session_state and the cookie so it survives a reload."""
    st.session_state[_QUEUE_STATE_KEY] = queue
    write_pending_queue(encode_queue(queue) if queue else "")


def pending_count() -> int:
    return len(get_queue())


def enqueue_site_log(record: dict) -> bool:
    """Park a prebuilt site-log record for later sync. Returns False if the queue is
    full (caller must tell the user to sync before logging more), True if accepted."""
    queue = get_queue()
    new_queue, accepted = add_entry(queue, make_entry("site_log", record))
    if accepted:
        persist_queue(new_queue)
        logger.info("Queued a site-log entry offline (%d pending)", len(new_queue))
    return accepted


def drain(sync_fn) -> tuple[int, int]:
    """Try to sync every queued entry via sync_fn(kind, payload) -> bool.

    Removes each entry that syncs successfully; leaves the rest queued (e.g. still
    offline) for the next attempt. Returns (synced, remaining). sync_fn must return
    truthy only on a confirmed write so we never drop an entry that didn't land.
    """
    queue = get_queue()
    synced = 0
    for entry in list(queue):
        try:
            ok = sync_fn(entry.get("kind"), entry.get("payload"))
        except Exception:
            logger.warning("Sync of a queued entry raised; leaving it queued", exc_info=True)
            ok = False
        if ok:
            queue = remove_entry(queue, entry["id"])
            synced += 1
        else:
            # Stop at the first failure: if we're offline again, the rest will fail
            # too, and retrying them just burns time and duplicates error noise.
            break
    persist_queue(queue)
    return synced, len(queue)
