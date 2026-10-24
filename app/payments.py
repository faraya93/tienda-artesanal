"""Webpay Plus via the official Transbank SDK. Card data never touches this app."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from transbank.common.integration_type import IntegrationType
from transbank.common.options import WebpayOptions
from transbank.webpay.webpay_plus.transaction import Transaction

INTEGRATION_HOST = "webpay3gint.transbank.cl"
PRODUCTION_HOST = "webpay3g.transbank.cl"
_INTEGRATION_ALIASES = {"", "integration", "test", "integracion"}
_PRODUCTION_ALIASES = {"production", "live", "produccion"}


class PaymentsConfigError(RuntimeError):
    pass


def environment_name() -> str:
    raw = os.environ.get("TRANSBANK_ENVIRONMENT", "integration").strip().lower()
    if raw in _INTEGRATION_ALIASES:
        return "integration"
    if raw in _PRODUCTION_ALIASES:
        return "production"
    raise PaymentsConfigError(
        "TRANSBANK_ENVIRONMENT debe ser integration o production."
    )


def expected_host() -> str:
    return PRODUCTION_HOST if environment_name() == "production" else INTEGRATION_HOST


def validate_redirect_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != expected_host():
        raise PaymentsConfigError("La dirección de Webpay no es la esperada.")
    return url


def create_webpay_transaction(buy_order: str, session_id: str, amount: int, return_url: str) -> dict:
    response = _transaction().create(str(buy_order), str(session_id), int(amount), return_url)
    if not isinstance(response, dict) or "token" not in response or "url" not in response:
        raise PaymentsConfigError("Webpay no entregó token y URL.")
    return {"token": response["token"], "url": validate_redirect_url(response["url"])}


def commit_webpay_transaction(token: str) -> dict:
    response = _transaction().commit(token)
    if not isinstance(response, dict):
        raise PaymentsConfigError("Webpay no confirmó la transacción.")
    return response


def is_approved(result: dict, *, buy_order: str, session_id: str, total_clp: int) -> bool:
    try:
        code = int(result.get("response_code"))
    except (TypeError, ValueError):
        return False
    amount = _as_clp(result.get("amount"))
    echoed_session = result.get("session_id")
    if echoed_session and echoed_session != session_id:
        return False
    return (
        code == 0
        and result.get("status") == "AUTHORIZED"
        and result.get("buy_order") == buy_order
        and amount == int(total_clp)
    )


def _transaction() -> Transaction:
    code = os.environ.get("TRANSBANK_COMMERCE_CODE", "").strip()
    api_key = os.environ.get("TRANSBANK_API_KEY", "").strip()
    if not code or not api_key:
        raise PaymentsConfigError("Faltan TRANSBANK_COMMERCE_CODE o TRANSBANK_API_KEY.")
    integration_type = (
        IntegrationType.LIVE if environment_name() == "production" else IntegrationType.TEST
    )
    return Transaction(WebpayOptions(code, api_key, integration_type, timeout=30))


def _as_clp(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            return None
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
