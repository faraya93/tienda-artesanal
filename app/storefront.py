"""Public storefront. Prices always come from SQLite, never from the browser."""

from __future__ import annotations

import re
import secrets
import time

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from app import payments
from app.db import (
    CATEGORIES,
    cover_of,
    create_order,
    get_db,
    get_order_by_buy_order,
    get_order_by_token,
    get_product,
    list_media,
    list_products,
    mark_failed,
    mark_paid,
    order_items,
    set_order_token,
)
from app.formatting import STATUS_LABELS, clip_text
from app.payments import PaymentsConfigError
from app.uploads import STORED_NAME_RE
from transbank.error.transbank_error import TransbankError

bp = Blueprint("storefront", __name__)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_BUY_ORDER = re.compile(r"^T[0-9a-f]{17}$")


@bp.get("/")
def home():
    category = request.args.get("categoria", "").strip()
    if category not in CATEGORIES:
        category = ""
    products = list_products(get_db(), category=category or None, active_only=True)
    store = _store_name()
    description = "Carteras, telares y pulseras hechos a mano en talleres de Chile."
    if category:
        description = f"{category} hechas a mano en Chile. {description}"
    return render_template(
        "home.html",
        products=products,
        current_category=category,
        og=_og(
            title=f"{store} · Hecho a mano en Chile",
            description=description,
            image=_absolute_media(products[0]["cover"]) if products and products[0]["cover"] else "",
            kind="website",
        ),
    )


@bp.get("/producto/<int:product_id>")
def product(product_id: int):
    row = get_product(get_db(), product_id)
    if row is None or not row["active"]:
        abort(404)
    media = list_media(get_db(), product_id)
    cover = cover_of(media)
    store = _store_name()
    return render_template(
        "product.html",
        product=row,
        media=media,
        cover=cover,
        og=_og(
            title=f"{row['name']} · {store}",
            description=clip_text(row["description"]),
            image=_absolute_media(cover["filename"]) if cover else "",
            kind="product",
        ),
    )


@bp.get("/medios/<filename>")
def media_file(filename: str):
    if not STORED_NAME_RE.fullmatch(filename):
        abort(404)
    response = send_from_directory(current_app.config["MEDIA_FOLDER"], filename)
    response.cache_control.public = True
    response.cache_control.max_age = 86400
    return response


@bp.post("/carro/agregar")
def cart_add():
    try:
        product_id = int(request.form.get("product_id", ""))
        quantity = int(request.form.get("quantity", "1"))
    except ValueError:
        abort(400)
    row = get_product(get_db(), product_id)
    if row is None or not row["active"]:
        abort(404)
    if row["stock"] < 1:
        flash("Esa pieza está agotada.")
        return redirect(url_for("storefront.product", product_id=product_id))
    quantity = max(1, min(quantity, row["stock"]))
    cart = _cart()
    key = str(product_id)
    cart[key] = min(row["stock"], int(cart.get(key, 0)) + quantity)
    session["cart"] = cart
    session.modified = True
    flash(f"Agregaste {row['name']} al carro.")
    return redirect(url_for("storefront.cart"))


@bp.post("/carro/actualizar")
def cart_update():
    cart = _cart()
    remove_id = request.form.get("quitar", "").strip()
    if remove_id:
        cart.pop(remove_id, None)
        session["cart"] = cart
        session.modified = True
        return redirect(url_for("storefront.cart"))
    updated = {}
    for key in list(cart):
        raw = request.form.get(f"qty_{key}", "")
        try:
            qty = int(raw)
        except ValueError:
            qty = int(cart[key])
        if qty > 0:
            updated[key] = qty
    session["cart"] = updated
    session.modified = True
    return redirect(url_for("storefront.cart"))


@bp.get("/carro")
def cart():
    lines, total, _notices = _resolve_cart(flash_notices=True)
    store = _store_name()
    return render_template(
        "cart.html",
        lines=lines,
        total=total,
        og=_og(
            title=f"Carro · {store}",
            description="Revisa tus piezas antes de pagar con Webpay.",
            image=lines[0]["cover"] if lines else "",
            kind="website",
        ),
    )


@bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    lines, total, _notices = _resolve_cart(flash_notices=True)
    if not lines or any(line["quantity"] < 1 for line in lines):
        flash("Tu carro está vacío.")
        return redirect(url_for("storefront.cart"))
    draft = {
        "nombre": request.form.get("nombre", ""),
        "email": request.form.get("email", ""),
        "telefono": request.form.get("telefono", ""),
        "direccion": request.form.get("direccion", ""),
        "ciudad": request.form.get("ciudad", ""),
        "notas": request.form.get("notas", ""),
    }
    errors: list[str] = []
    if request.method == "POST":
        customer, errors = _customer(draft)
        if not errors:
            return _start_payment(lines, total, customer)
    store = _store_name()
    return render_template(
        "checkout.html",
        lines=lines,
        total=total,
        draft=draft,
        errors=errors,
        og=_og(
            title=f"Pago · {store}",
            description="Paga con Webpay. No guardamos los datos de tu tarjeta.",
            image=lines[0]["cover"] if lines else "",
            kind="website",
        ),
    )


@bp.route("/pago/retorno", methods=["GET", "POST"])
def webpay_return():
    """Browser return from Webpay. Four cases, matching Transbank's docs:

    - only token_ws: commit and read the result (approved or rejected)
    - TBK_TOKEN without token_ws, or both together: aborted, do not commit
    - only TBK_ORDEN_COMPRA / TBK_ID_SESION: timeout, do not commit
    """
    token_ws = _param("token_ws")
    tbk_token = _param("TBK_TOKEN")
    tbk_order = _param("TBK_ORDEN_COMPRA")
    connection = get_db()

    if not token_ws or tbk_token:
        order = get_order_by_token(connection, tbk_token) if tbk_token else None
        if order is None and tbk_order:
            order = get_order_by_buy_order(connection, tbk_order)
        if order is None:
            abort(404)
        mark_failed(connection, order["id"])
        return redirect(url_for("storefront.confirmation", buy_order=order["buy_order"]))

    order = get_order_by_token(connection, token_ws)
    if order is None:
        abort(404)
    if order["status"] != "pending":
        return redirect(url_for("storefront.confirmation", buy_order=order["buy_order"]))

    try:
        result = payments.commit_webpay_transaction(token_ws)
    except (PaymentsConfigError, TransbankError) as exc:
        current_app.logger.warning("Webpay commit failed: %s", exc)
        flash("No pudimos confirmar el pago con Webpay. Si se cobró, el pedido sigue pendiente.")
        return redirect(url_for("storefront.confirmation", buy_order=order["buy_order"]))

    current_app.logger.info(
        "Webpay commit buy_order=%s status=%s response_code=%s",
        order["buy_order"],
        result.get("status"),
        result.get("response_code"),
    )
    if payments.is_approved(
        result,
        buy_order=order["buy_order"],
        session_id=order["session_id"],
        total_clp=order["total_clp"],
    ):
        mark_paid(connection, order["id"])
        session["cart"] = {}
        session.modified = True
    else:
        mark_failed(connection, order["id"])
    return redirect(url_for("storefront.confirmation", buy_order=order["buy_order"]))


@bp.get("/pedido/<buy_order>")
def confirmation(buy_order: str):
    if not _BUY_ORDER.fullmatch(buy_order):
        abort(404)
    order = get_order_by_buy_order(get_db(), buy_order)
    if order is None:
        abort(404)
    store = _store_name()
    label = STATUS_LABELS.get(order["status"], order["status"])
    return render_template(
        "confirmation.html",
        order=order,
        items=order_items(order),
        status_label=label,
        og=_og(
            title=f"Pedido {order['id']} · {store}",
            description=f"Estado del pedido: {label}.",
            image="",
            kind="website",
        ),
    )


def _start_payment(lines, total, customer):
    connection = get_db()
    fresh, fresh_total, _notices = _resolve_cart(flash_notices=False)
    if not fresh or fresh_total != total or len(fresh) != len(lines):
        flash("El carro cambió. Revísalo antes de pagar.")
        return redirect(url_for("storefront.checkout"))
    # Recompute from the second read so the charged total is the database price.
    lines, total = fresh, fresh_total
    buy_order = _new_buy_order(connection)
    webpay_session = secrets.token_hex(16)
    items = [
        {
            "product_id": line["id"],
            "name": line["name"],
            "price_clp": line["price_clp"],
            "quantity": line["quantity"],
            "line_total": line["line_total"],
        }
        for line in lines
    ]
    order_id = create_order(
        connection,
        total_clp=total,
        customer_name=customer["nombre"],
        email=customer["email"],
        phone=customer["telefono"],
        address=customer["direccion"],
        city=customer["ciudad"],
        notes=customer["notas"],
        items=items,
        buy_order=buy_order,
        session_id=webpay_session,
    )
    connection.commit()
    return_url = url_for("storefront.webpay_return", _external=True)
    try:
        created = payments.create_webpay_transaction(buy_order, webpay_session, total, return_url)
        payments.validate_redirect_url(created["url"])
    except (PaymentsConfigError, TransbankError) as exc:
        current_app.logger.warning("Webpay create failed: %s", exc)
        mark_failed(connection, order_id)
        flash("No pudimos iniciar el pago en Webpay. No se hizo ningún cobro.")
        return redirect(url_for("storefront.checkout"))
    set_order_token(connection, order_id, created["token"])
    connection.commit()
    return render_template(
        "webpay_redirect.html",
        webpay_url=created["url"],
        webpay_token=created["token"],
        total=total,
        buy_order=buy_order,
        og=_og(
            title=f"Webpay · {_store_name()}",
            description="Te estamos llevando a Webpay para pagar.",
            image="",
            kind="website",
        ),
    )


def _resolve_cart(*, flash_notices: bool):
    raw = _cart()
    connection = get_db()
    lines = []
    total = 0
    cleaned = {}
    notices = []
    for key, raw_qty in list(raw.items()):
        try:
            product_id = int(key)
            quantity = int(raw_qty)
        except (TypeError, ValueError):
            continue
        row = get_product(connection, product_id)
        if row is None or not row["active"]:
            notices.append("Sacamos una pieza que ya no está disponible.")
            continue
        if quantity < 1 or row["stock"] < 1:
            notices.append(f"«{row['name']}» se agotó.")
            continue
        if quantity > row["stock"]:
            quantity = row["stock"]
            notices.append(f"Ajustamos «{row['name']}» al stock disponible.")
        line_total = row["price_clp"] * quantity
        total += line_total
        cleaned[str(product_id)] = quantity
        media = list_media(connection, product_id)
        cover = cover_of(media)
        lines.append(
            {
                "id": row["id"],
                "name": row["name"],
                "price_clp": row["price_clp"],
                "quantity": quantity,
                "line_total": line_total,
                "stock": row["stock"],
                "cover": _absolute_media(cover["filename"]) if cover else "",
                "cover_filename": cover["filename"] if cover else "",
            }
        )
    session["cart"] = cleaned
    session.modified = True
    if flash_notices:
        for notice in notices:
            flash(notice)
    return lines, total, notices


def _customer(draft: dict) -> tuple[dict, list[str]]:
    errors = []
    name = draft["nombre"].strip()
    email = draft["email"].strip()
    phone = draft["telefono"].strip()
    address = draft["direccion"].strip()
    city = draft["ciudad"].strip()
    notes = draft["notas"].strip()
    if len(name) < 2 or len(name) > 80:
        errors.append("Escribe tu nombre.")
    if not _EMAIL.fullmatch(email) or len(email) > 100:
        errors.append("Escribe un correo válido.")
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8 or len(phone) > 20:
        errors.append("Escribe un teléfono con al menos 8 dígitos.")
    if len(address) < 5 or len(address) > 200:
        errors.append("Escribe la dirección de entrega.")
    if len(city) < 2 or len(city) > 80:
        errors.append("Escribe la ciudad.")
    if len(notes) > 500:
        errors.append("Las notas pueden tener hasta 500 caracteres.")
    cleaned = {
        "nombre": name,
        "email": email,
        "telefono": phone,
        "direccion": address,
        "ciudad": city,
        "notas": notes,
    }
    return cleaned, errors


def _new_buy_order(connection) -> str:
    for _ in range(5):
        buy_order = f"T{int(time.time()) % 1_000_000_000:09d}{secrets.token_hex(4)}"
        if get_order_by_buy_order(connection, buy_order) is None:
            return buy_order
    raise RuntimeError("No pude generar un número de pedido.")


def _cart() -> dict:
    cart = session.get("cart")
    if not isinstance(cart, dict):
        cart = {}
    return cart


def _param(name: str) -> str:
    return (request.form.get(name) or request.args.get(name) or "").strip()


def _store_name() -> str:
    from os import environ

    return environ.get("STORE_NAME", "").strip() or "Taller Raíz"


def _absolute_media(filename: str | None) -> str:
    if not filename:
        return ""
    return url_for("storefront.media_file", filename=filename, _external=True)


def _og(*, title: str, description: str, image: str, kind: str) -> dict:
    return {
        "title": title,
        "description": description,
        "image": image,
        "type": kind,
        "url": request.url,
    }

