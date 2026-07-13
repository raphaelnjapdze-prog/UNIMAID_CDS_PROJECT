"""Every Supabase write must go through the client that carries the user's token.

utils/auth.py::get_supabase_client() re-applies the signed-in user's access token on
every call, because a Streamlit rerun can drop the shared client back to anon. A module
that reaches for the *base* client instead writes as anon — and under RLS those writes are
rejected, so the feature silently does not work in production while passing every test.

utils/pcr_and_accuracy.py did exactly that: it defined its own get_supabase_client()
returning get_base_supabase_client(), so every PCR confirmation was an anon write.
"""
import ast
import pathlib

import pytest

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
