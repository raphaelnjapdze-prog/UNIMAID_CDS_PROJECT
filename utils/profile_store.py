"""Persistence for investigator profiles.

Profiles used to be written to data/profiles/<uid>_profile.json with the avatar as a .png
beside it. Streamlit Cloud's filesystem is ephemeral — every reboot and redeploy wipes the
container — so a user's profile and photo silently vanished. They live in Supabase now,
like every other piece of state the app owns.

If Supabase isn't configured these functions return None / False and the caller shows a
"not connected" state. They never fall back to fabricating or locally caching a profile:
a profile that saves to nowhere is worse than one that honestly refuses to save.

Schema: sql/add_investigator_profiles.sql
"""

import uuid
from datetime import datetime, timezone

import streamlit as st

from utils.auth import get_supabase_client
from utils.data_manager import first_row
from utils.logging_config import get_logger

logger = get_logger(__name__)

PROFILE_TABLE = "investigator_profiles"
AVATAR_BUCKET = "profile-avatars"


def load_profile(user_id: str) -> dict | None:
    """The stored profile row for a user, or None if unavailable/not yet saved."""
    if not user_id:
        return None
    client = get_supabase_client()
    if client is None:
        return None

    try:
        response = (
            client.table(PROFILE_TABLE).select("*").eq("user_id", user_id).execute()
        )
    except Exception:
        logger.warning("Could not load investigator profile for %s", user_id, exc_info=True)
        return None
    return first_row(response)


def upload_avatar(user_id: str, image_bytes: bytes, ext: str = "png") -> str | None:
    """Upload an avatar and return its public URL, or None on failure.

    The object path is uniquely suffixed rather than overwritten in place: a stable path
    would keep serving the old image from CDN/browser cache after a change, so the user
    would upload a new photo and appear to see nothing happen.
    """
    client = get_supabase_client()
    if client is None or not image_bytes:
        return None

    path = f"{user_id}/{uuid.uuid4()}.{ext}"
    try:
        client.storage.from_(AVATAR_BUCKET).upload(
            path, image_bytes, {"content-type": f"image/{'jpeg' if ext in ('jpg', 'jpeg') else 'png'}"}
        )
        return client.storage.from_(AVATAR_BUCKET).get_public_url(path)
    except Exception as e:
        logger.warning("Avatar upload failed for %s", user_id, exc_info=True)
        st.warning(f"Photo upload failed, the rest of the profile will still be saved: {e}")
        return None


def save_profile(user_id: str, profile: dict, avatar_url: str | None = None) -> bool:
    """Upsert a user's profile. Returns False (having shown an error) if it didn't save."""
    if not user_id:
        st.error("You must be signed in to save your profile.")
        return False

    client = get_supabase_client()
    if client is None:
        st.error("Supabase is not configured — your profile cannot be saved.")
        return False

    record = {
        "user_id": user_id,
        "profile": profile,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Only overwrite the avatar when a new one was uploaded; otherwise a plain text edit
    # would blank out the existing photo.
    if avatar_url:
        record["avatar_url"] = avatar_url

    try:
        response = (
            client.table(PROFILE_TABLE).upsert(record, on_conflict="user_id").execute()
        )
    except Exception as e:
        logger.exception("Could not save investigator profile for %s", user_id)
        st.error(f"Could not save your profile: {e}")
        return False

    if first_row(response) is None:
        # An upsert no RLS policy permits matches nothing and raises nothing — exactly the
        # failure that made every specimen UPDATE a silent no-op. Say so rather than
        # reporting a save that did not happen.
        logger.warning("Profile upsert for %s matched no rows", user_id)
        st.error(
            "Your profile was not saved — the database accepted no change. Check that "
            "sql/add_investigator_profiles.sql has been run."
        )
        return False
    return True
