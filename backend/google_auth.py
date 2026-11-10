"""Google ID-token verification for the QA dashboard.

Env:
  QA_DASHBOARD_GOOGLE_CLIENT_ID  — OAuth 2.0 Web client ID from Google Cloud Console
  QA_DASHBOARD_ALLOWED_DOMAINS   — optional, comma-separated (e.g. agungsedayu.com,sedayuone.com)
                                  Empty = allow any verified Google email (including gmail.com).
  QA_DASHBOARD_ALLOWED_EMAILS    — optional, comma-separated single addresses allowed in
                                  addition to the domains (e.g. someone@gmail.com).
                                  If both lists are empty, anyone may sign in.
"""

from __future__ import annotations

import os
from typing import Optional

GOOGLE_CLIENT_ID = (os.environ.get("QA_DASHBOARD_GOOGLE_CLIENT_ID") or "").strip()

ALLOWED_DOMAINS = {
    d.strip().lower()
    for d in os.environ.get("QA_DASHBOARD_ALLOWED_DOMAINS", "").split(",")
    if d.strip()
}


ALLOWED_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("QA_DASHBOARD_ALLOWED_EMAILS", "").split(",")
    if e.strip()
}


def email_allowed(email: str) -> bool:
    """True if this address may sign in or sign up (Google and password)."""
    email = (email or "").strip().lower()
    if not ALLOWED_DOMAINS and not ALLOWED_EMAILS:
        return True
    if email in ALLOWED_EMAILS:
        return True
    return email.rsplit("@", 1)[-1] in ALLOWED_DOMAINS


def google_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID)


def verify_google_id_token(credential: str) -> dict:
    """Verify a Google Identity Services ID token.

    Returns a dict with at least: email, name (optional), sub.
    Raises ValueError with a safe message on failure.
    """
    if not GOOGLE_CLIENT_ID:
        raise ValueError("Google sign-in is not configured on the server")

    credential = (credential or "").strip()
    if not credential:
        raise ValueError("Missing Google credential")

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
    except ImportError as exc:
        raise ValueError(
            "Server is missing the google-auth package. Run: pip install google-auth"
        ) from exc

    try:
        idinfo = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        raise ValueError("Invalid or expired Google token") from exc

    if idinfo.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("Invalid Google token issuer")

    email = (idinfo.get("email") or "").strip().lower()
    if not email:
        raise ValueError("Google account has no email")
    if not idinfo.get("email_verified", False):
        raise ValueError("Google email is not verified")

    if not email_allowed(email):
        raise ValueError("Sign-in is limited to approved company email addresses")

    return {
        "email": email,
        "name": (idinfo.get("name") or "").strip() or None,
        "sub": idinfo.get("sub"),
    }