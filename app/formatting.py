"""CLP amounts and small text helpers. Prices are integer pesos, never cents."""

from __future__ import annotations

import re
from datetime import datetime

MAX_PRICE_CLP = 50_000_000
MAX_STOCK = 100_000

STATUS_LABELS = {
    "pending": "Pendiente",
    "paid": "Pagado",
    "failed": "Rechazado",
}

_THOUSANDS = re.compile(r"\d{1,3}(\.\d{3})+")
_DIGITS = re.compile(r"\d+")


def format_clp(amount: int) -> str:
    """Format an integer peso amount as $12.990."""
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise TypeError("el precio debe ser un entero")
    sign = "-" if amount < 0 else ""
    grouped = f"{abs(amount):,}".replace(",", ".")
    return f"{sign}${grouped}"


def parse_price(value: object) -> int:
    number = _parse_whole(value, label="precio")
    if number < 1 or number > MAX_PRICE_CLP:
        raise ValueError("El precio tiene que ser un entero entre 1 y 50.000.000.")
    return number


def parse_stock(value: object) -> int:
    number = _parse_whole(value, label="stock")
    if number < 0 or number > MAX_STOCK:
        raise ValueError("El stock tiene que ser un entero entre 0 y 100.000.")
    return number


def format_when(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d-%m-%Y %H:%M")
    except (TypeError, ValueError):
        return value or ""


def clip_text(text: str, limit: int = 160) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _parse_whole(value: object, *, label: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"El {label} tiene que ser un número entero.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"El {label} tiene que ser un entero, sin decimales.")
        return int(value)
    text = str(value).strip().replace("$", "").replace(" ", "")
    if _THOUSANDS.fullmatch(text) or _DIGITS.fullmatch(text):
        return int(text.replace(".", ""))
    raise ValueError(
        f"El {label} tiene que ser un entero. En el Excel escribe 12990, no 12.990 con decimales."
    )
