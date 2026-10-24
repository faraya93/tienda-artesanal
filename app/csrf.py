"""Session CSRF token on every POST except the Webpay browser return."""

from __future__ import annotations

import hmac
import secrets

from flask import abort, request, session


def ensure_csrf_token() -> str:
    token = session.get("csrf_token")
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_hex(32)
        session["csrf_token"] = token
    return token


def validate_csrf() -> None:
    token = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if (
        not isinstance(token, str)
        or not isinstance(expected, str)
        or not token
        or not expected
        or not hmac.compare_digest(token, expected)
    ):
        abort(400)
