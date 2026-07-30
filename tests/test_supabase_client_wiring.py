"""Every Supabase write must go through the client that carries the user's token.

utils/auth.py::get_supabase_client() re-applies the signed-in user's access token on
every call, because a Streamlit rerun can drop the shared client back to anon. A module
that reaches for the *base* client instead writes as anon — and under RLS those writes are
rejected, so the feature silently does not work in production while passing every test.

utils/pcr_and_accuracy.py did exactly that: it defined its own get_supabase_client()
returning get_base_supabase_client(), so every PCR confirmation was an anon write.

The same failure has a second form, further down: reaching the right client but failing to
get the token onto the request. Storage kept two header stores and only one reached the
wire, so photo uploads were anon and RLS rejected every one of them. The tests at the
bottom assert against the bytes storage3 actually sends, not against the attribute we set.
"""
import ast
import pathlib

import httpx
import pytest
from storage3 import SyncStorageClient

import utils.auth as auth

# Modules that persist data. Read-only helpers may legitimately use the base client.
WRITER_MODULES = [
    "utils/data_manager.py",
    "utils/specimen_submission.py",
    "utils/pcr_and_accuracy.py",
]


@pytest.mark.parametrize("path", WRITER_MODULES)
def test_writers_do_not_import_the_base_client(path):
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "get_base_supabase_client" not in imported, (
        f"{path} imports the base (anon) Supabase client. Writes made with it are "
        f"rejected by RLS. Use utils.auth.get_supabase_client, which re-applies the "
        f"user's token on every call."
    )


@pytest.mark.parametrize("path", WRITER_MODULES)
def test_writers_do_not_shadow_get_supabase_client(path):
    """A local def of get_supabase_client silently overrides the imported one."""
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    local_defs = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "get_supabase_client"
    ]
    assert not local_defs, (
        f"{path} defines its own get_supabase_client, shadowing the token-aware one in "
        f"utils.auth. That is how the PCR page ended up writing as anon."
    )


def test_pcr_module_uses_the_auth_client():
    import utils.pcr_and_accuracy as pcr

    assert pcr.get_supabase_client is auth.get_supabase_client


# ---------------------------------------------------------------------------
# Storage uploads must carry the user's token, not the anon key.
# ---------------------------------------------------------------------------
ANON = "Bearer ANON_KEY"
USER = "USER_ACCESS_TOKEN"


class _StubClient:
    """Just enough of a Supabase client for _apply_storage_token: a .storage."""

    def __init__(self, storage):
        self.storage = storage


def _storage_client(sent):
    """A real SyncStorageClient whose requests are captured instead of sent.

    Built the way supabase-py builds it — anon headers baked in at construction — so the
    two header stores exist exactly as they do in production.
    """
    def handler(request):
        sent.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"Key": "specimen-photos/x.jpg"})

    anon_headers = {"Authorization": ANON, "apikey": "ANON_KEY"}
    return SyncStorageClient(
        "https://stub.supabase.co/storage/v1/",
        anon_headers,
        http_client=httpx.Client(transport=httpx.MockTransport(handler), headers=anon_headers),
    )


def _upload(storage):
    storage.from_("specimen-photos").upload(
        "SPEC-1/photo.jpg", b"jpegbytes", {"content-type": "image/jpeg"}
    )


def test_upload_sends_the_user_token():
    sent = []
    storage = _storage_client(sent)
    auth._apply_storage_token(_StubClient(storage), USER)
    _upload(storage)

    assert sent == [f"Bearer {USER}"], (
        "The upload went out as anon. Storage RLS rejects it with 'new row violates "
        "row-level security policy' and the photo is silently dropped."
    )


def test_upload_through_a_proxy_built_before_the_token_was_applied():
    """from_() hands the header object out by reference, so an existing proxy sees it too.

    get_supabase_client() re-applies the token on every call, which can land after a
    bucket proxy already exists. Mutating in place is what makes that safe; rebinding
    _headers to a new object would leave the old proxy on the anon key.
    """
    sent = []
    storage = _storage_client(sent)
    proxy = storage.from_("specimen-photos")
    auth._apply_storage_token(_StubClient(storage), USER)
    proxy.upload("SPEC-1/photo.jpg", b"jpegbytes", {"content-type": "image/jpeg"})

    assert sent == [f"Bearer {USER}"]


def test_setting_only_the_session_header_is_not_enough():
    """Pins the reason the fix is shaped the way it is.

    This is what the code did before: storage3's _request() passes its own _headers to
    httpx explicitly, and an explicit request header beats the session default — so this
    assignment never reached the wire. If storage3 ever stops overriding, this test fails
    and _apply_storage_token can be simplified; until then, don't 'tidy' it back.
    """
    sent = []
    storage = _storage_client(sent)
    storage._client.headers["Authorization"] = f"Bearer {USER}"
    _upload(storage)

    assert sent == [ANON]
