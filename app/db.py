"""SQLite schema and queries. Callers commit; money and stock changes commit here."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app, g

CATEGORIES = ("Carteras", "Telares", "Pulseras", "Otros")
SANTIAGO = ZoneInfo("America/Santiago")

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    price_clp INTEGER NOT NULL CHECK (price_clp > 0),
    category TEXT NOT NULL CHECK (category IN ('Carteras', 'Telares', 'Pulseras', 'Otros')),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN ('image', 'video')),
    position INTEGER NOT NULL CHECK (position >= 0),
    UNIQUE (product_id, position)
);

CREATE INDEX IF NOT EXISTS idx_media_product ON media(product_id, position);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'failed')),
    total_clp INTEGER NOT NULL CHECK (total_clp >= 0),
    customer_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    items_json TEXT NOT NULL,
    buy_order TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    tbk_token TEXT,
    created_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(SANTIAGO).isoformat(timespec="minutes")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_error=None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db(app) -> None:
    with app.app_context():
        connection = get_db()
        connection.executescript(SCHEMA)
        connection.commit()


def count_products(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]


def create_product(
    connection: sqlite3.Connection,
    *,
    name: str,
    description: str,
    price_clp: int,
    category: str,
    stock: int,
    active: int = 1,
    created_at: str | None = None,
) -> int:
    if category not in CATEGORIES:
        raise ValueError(category)
    cursor = connection.execute(
        """
        INSERT INTO products (name, description, price_clp, category, stock, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            description,
            int(price_clp),
            category,
            int(stock),
            1 if active else 0,
            created_at or now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def update_product(
    connection: sqlite3.Connection,
    product_id: int,
    *,
    name: str,
    description: str,
    price_clp: int,
    category: str,
    stock: int,
    active: int,
) -> None:
    connection.execute(
        """
        UPDATE products
        SET name = ?, description = ?, price_clp = ?, category = ?, stock = ?, active = ?
        WHERE id = ?
        """,
        (name, description, int(price_clp), category, int(stock), 1 if active else 0, product_id),
    )


def get_product(connection: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()


def list_products(
    connection: sqlite3.Connection,
    *,
    category: str | None = None,
    active_only: bool = True,
) -> list[sqlite3.Row]:
    sql = """
        SELECT p.*,
            (
                SELECT m.filename FROM media m
                WHERE m.product_id = p.id AND m.media_type = 'image'
                ORDER BY m.position ASC, m.id ASC
                LIMIT 1
            ) AS cover
        FROM products p
        WHERE 1 = 1
    """
    params: list[object] = []
    if active_only:
        sql += " AND p.active = 1"
    if category is not None:
        sql += " AND p.category = ?"
        params.append(category)
    sql += " ORDER BY p.created_at DESC, p.id DESC"
    return list(connection.execute(sql, params))


def delete_product(connection: sqlite3.Connection, product_id: int) -> list[str]:
    filenames = [
        row["filename"]
        for row in connection.execute(
            "SELECT filename FROM media WHERE product_id = ?", (product_id,)
        )
    ]
    connection.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return filenames


def list_media(connection: sqlite3.Connection, product_id: int) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT * FROM media
            WHERE product_id = ?
            ORDER BY position ASC, id ASC
            """,
            (product_id,),
        )
    )


def cover_of(media_rows: list[sqlite3.Row]):
    """Position 0 image is the cover. Fall back to the first image."""
    for row in media_rows:
        if row["media_type"] == "image" and row["position"] == 0:
            return row
    for row in media_rows:
        if row["media_type"] == "image":
            return row
    return None


def replace_media(connection: sqlite3.Connection, product_id: int, items: list[dict]) -> None:
    connection.execute("DELETE FROM media WHERE product_id = ?", (product_id,))
    for position, item in enumerate(items):
        connection.execute(
            """
            INSERT INTO media (product_id, filename, media_type, position)
            VALUES (?, ?, ?, ?)
            """,
            (product_id, item["filename"], item["media_type"], position),
        )


def create_order(
    connection: sqlite3.Connection,
    *,
    total_clp: int,
    customer_name: str,
    email: str,
    phone: str,
    address: str,
    city: str,
    notes: str,
    items: list[dict],
    buy_order: str,
    session_id: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO orders (
            status, total_clp, customer_name, email, phone, address, city, notes,
            items_json, buy_order, session_id, tbk_token, created_at
        ) VALUES ('pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            int(total_clp),
            customer_name,
            email,
            phone,
            address,
            city,
            notes,
            json.dumps(items, ensure_ascii=False),
            buy_order,
            session_id,
            now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def set_order_token(connection: sqlite3.Connection, order_id: int, token: str) -> None:
    connection.execute("UPDATE orders SET tbk_token = ? WHERE id = ?", (token, order_id))


def get_order(connection: sqlite3.Connection, order_id: int) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def get_order_by_buy_order(connection: sqlite3.Connection, buy_order: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM orders WHERE buy_order = ?", (buy_order,)
    ).fetchone()


def get_order_by_token(connection: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM orders WHERE tbk_token = ?", (token,)).fetchone()


def list_orders(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(connection.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 200"))


def count_orders(connection: sqlite3.Connection, status: str) -> int:
    return connection.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE status = ?", (status,)
    ).fetchone()["n"]


def mark_paid(connection: sqlite3.Connection, order_id: int) -> bool:
    """Mark a pending order paid and decrement stock once. Stock never goes below 0."""
    cursor = connection.execute(
        "UPDATE orders SET status = 'paid' WHERE id = ? AND status = 'pending'",
        (order_id,),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        return False
    order = connection.execute(
        "SELECT items_json FROM orders WHERE id = ?", (order_id,)
    ).fetchone()
    for item in json.loads(order["items_json"]):
        connection.execute(
            "UPDATE products SET stock = MAX(stock - ?, 0) WHERE id = ?",
            (int(item["quantity"]), int(item["product_id"])),
        )
    connection.commit()
    return True


def mark_failed(connection: sqlite3.Connection, order_id: int) -> bool:
    cursor = connection.execute(
        "UPDATE orders SET status = 'failed' WHERE id = ? AND status = 'pending'",
        (order_id,),
    )
    changed = cursor.rowcount == 1
    connection.commit()
    return changed


def order_items(order: sqlite3.Row) -> list[dict]:
    return json.loads(order["items_json"])
