"""Artisan store application factory."""

from __future__ import annotations

import os
import re
import sys

from dotenv import load_dotenv
from flask import Flask, render_template, request, session, url_for

from app.csrf import ensure_csrf_token, validate_csrf
from app.db import CATEGORIES, close_db, get_db, init_db
from app.formatting import STATUS_LABELS, format_clp, format_when

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PIXEL = re.compile(r"[0-9]{5,20}")


def create_app(test_config: dict | None = None) -> Flask:
    if sys.version_info < (3, 13):
        raise RuntimeError("Se necesita Python 3.13 o superior.")

    load_dotenv(os.path.join(ROOT, ".env"), override=False)
    app = Flask(
        __name__,
        instance_path=os.path.join(ROOT, "instance"),
        template_folder=os.path.join(ROOT, "templates"),
        static_folder=os.path.join(ROOT, "static"),
    )
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "").strip(),
        DATABASE=os.path.join(ROOT, "instance", "tienda.sqlite"),
        MEDIA_FOLDER=os.path.join(ROOT, "instance", "media"),
        MAX_CONTENT_LENGTH=512 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        TEMPLATES_AUTO_RELOAD=True,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Define FLASK_SECRET_KEY en el entorno o en .env.")

    app.url_map.strict_slashes = False
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(os.path.dirname(app.config["DATABASE"]) or ".", exist_ok=True)
    os.makedirs(app.config["MEDIA_FOLDER"], exist_ok=True)

    from app.admin import bp as admin_bp
    from app.storefront import bp as storefront_bp

    app.register_blueprint(storefront_bp)
    app.register_blueprint(admin_bp)
    app.teardown_appcontext(close_db)
    init_db(app)

    @app.before_request
    def _csrf():
        ensure_csrf_token()
        if request.method == "POST" and request.endpoint != "storefront.webpay_return":
            validate_csrf()

    @app.context_processor
    def _inject():
        return {
            "store_name": os.environ.get("STORE_NAME", "").strip() or "Taller Raíz",
            "csrf_token": session.get("csrf_token", ""),
            "cart_count": _cart_count(),
            "format_clp": format_clp,
            "format_when": format_when,
            "meta_pixel_id": _pixel_id(),
            "categories": CATEGORIES,
            "status_labels": STATUS_LABELS,
            "default_og_image": _default_og_image(),
        }

    @app.errorhandler(400)
    def _bad_request(_error):
        return (
            render_template(
                "error.html",
                heading="El formulario expiró",
                message="Vuelve a intentar. Si estabas pagando, revisa el carro antes de enviar de nuevo.",
                og=_plain_og("Formulario rechazado"),
            ),
            400,
        )

    @app.errorhandler(404)
    def _not_found(_error):
        return (
            render_template(
                "error.html",
                heading="No encontramos esa página",
                message="La pieza o el pedido no está, o el enlace se cortó.",
                og=_plain_og("Página no encontrada"),
            ),
            404,
        )

    @app.errorhandler(413)
    def _too_large(_error):
        return (
            render_template(
                "error.html",
                heading="El archivo es demasiado grande",
                message="Cada imagen puede pesar hasta 5 MB y el video hasta 30 MB.",
                og=_plain_og("Archivo demasiado grande"),
            ),
            413,
        )

    @app.cli.command("seed")
    def seed_command():
        """Carga el catálogo de ejemplo si la base está vacía."""
        from app.seed import seed_if_empty

        count = seed_if_empty()
        print(f"Productos en el catálogo: {count}")

    if not app.config.get("TESTING"):
        with app.app_context():
            from app.seed import seed_if_empty

            seed_if_empty()

    return app


def _cart_count() -> int:
    cart = session.get("cart")
    if not isinstance(cart, dict):
        return 0
    total = 0
    for quantity in cart.values():
        try:
            total += max(int(quantity), 0)
        except (TypeError, ValueError):
            continue
    return total


def _pixel_id() -> str:
    raw = os.environ.get("META_PIXEL_ID", "").strip()
    if _PIXEL.fullmatch(raw):
        return raw
    return ""


def _default_og_image() -> str:
    try:
        row = get_db().execute(
            """
            SELECT m.filename
            FROM media m
            JOIN products p ON p.id = m.product_id
            WHERE p.active = 1 AND m.media_type = 'image' AND m.position = 0
            ORDER BY p.id ASC
            LIMIT 1
            """
        ).fetchone()
    except Exception:
        return ""
    if row is None:
        return ""
    return url_for("storefront.media_file", filename=row["filename"], _external=True)


def _plain_og(title: str) -> dict:
    store = os.environ.get("STORE_NAME", "").strip() or "Taller Raíz"
    return {
        "title": f"{title} · {store}",
        "description": "Tienda de piezas hechas a mano en Chile.",
        "image": "",
        "type": "website",
        "url": request.url,
    }
