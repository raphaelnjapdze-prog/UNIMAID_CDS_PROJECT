"""Tests for the local-admin authentication fallback in utils.auth.

The security-critical property: the offline admin login exists only when an
admin password is configured, and never accepts an empty/omitted password.
"""

import utils.auth as auth


def _patch_admin(monkeypatch, password):
    monkeypatch.setattr(auth, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(auth, "ADMIN_EMAIL", "admin@localhost")
    monkeypatch.setattr(auth, "ADMIN_PASSWORD", password)
    # Force the Supabase path off so we exercise the local fallback.
    monkeypatch.setattr(auth, "get_base_supabase_client", lambda: None)


def test_correct_credentials_succeed(monkeypatch):
    _patch_admin(monkeypatch, "secret")
    result = auth.sign_in_user("admin", "secret")
    # sign_in_user returns a Supabase AuthResponse (attribute access) on the online path
    # and a plain dict on this local-admin one. components/login.py branches on exactly
    # that, so pin the shape the fallback is contracted to return.
    assert isinstance(result, dict)
    assert result["user"]["email"] == "admin@localhost"


def test_login_by_email_also_works(monkeypatch):
    _patch_admin(monkeypatch, "secret")
    assert auth.sign_in_user("admin@localhost", "secret") is not None


def test_wrong_password_rejected(monkeypatch):
    _patch_admin(monkeypatch, "secret")
    assert auth.sign_in_user("admin", "wrong") is None


def test_fallback_disabled_when_no_password(monkeypatch):
    _patch_admin(monkeypatch, None)
    # With no admin password configured, no credential may unlock the fallback.
    assert auth.sign_in_user("admin", "") is None
    assert auth.sign_in_user("admin", "anything") is None


def test_unset_admin_identity_matches_nothing(monkeypatch):
    """An admin identity that was never configured must not be matchable.

    ADMIN_USERNAME/ADMIN_EMAIL come from secrets and may be unset. Coercing an unset one
    to "" would let a submitted empty email match it, handing out an admin session to a
    blank username.
    """
    monkeypatch.setattr(auth, "ADMIN_USERNAME", None)
    monkeypatch.setattr(auth, "ADMIN_EMAIL", None)
    monkeypatch.setattr(auth, "ADMIN_PASSWORD", "secret")
    monkeypatch.setattr(auth, "get_base_supabase_client", lambda: None)

    assert auth.sign_in_user("", "secret") is None
    assert auth.sign_in_user("   ", "secret") is None
    assert auth.sign_in_user("admin", "secret") is None
