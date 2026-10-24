"""Password-protected admin for a non-technical owner. No customer accounts."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from io import BytesIO

from app.db import (
    CATEGORIES,
    count_orders,
    cover_of,
    create_product,
    delete_product,
    get_db,
    get_product,
    list_media,
    list_orders,
    list_products,
    order_items,
    replace_media,
    update_product,
)
from app.formatting import STATUS_LABELS, parse_price, parse_stock
from app.importer import build_template, import_workbook, read_uploaded_media
from app.uploads import arrange_media, remove_file, save_bytes

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def require_login():
    if request.endpoint == "admin.login":
        return None
    if session.get("is_admin") is True:
        return None
    return redirect(url_for("admin.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("is_admin") is True and request.method == "GET":
        return redirect(url_for("admin.dashboard"))
    error = None
    if request.method == "POST":
        if _password_ok(request.form.get("password", "")):
            session["is_admin"] = True
            session["csrf_token"] = secrets.token_hex(32)
            return redirect(url_for("admin.dashboard"))
        if not os.environ.get("ADMIN_PASSWORD", "").strip():
            error = "Falta ADMIN_PASSWORD en la configuración."
        else:
            error = "Clave incorrecta."
    return render_template("admin/login.html", error=error, og=_page("Entrar", "Acceso de la tienda."))


@bp.post("/salir")
def logout():
    session.pop("is_admin", None)
    session["csrf_token"] = secrets.token_hex(32)
    flash("Cerraste la sesión.")
    return redirect(url_for("admin.login"))


@bp.get("/")
def dashboard():
    products = list_products(get_db(), active_only=False)
    pending = count_orders(get_db(), "pending")
    return render_template(
        "admin/dashboard.html",
        products=products,
        pending=pending,
        og=_page("Administración", "Piezas, pedidos e importación."),
    )


@bp.route("/productos/nuevo", methods=["GET", "POST"])
def new_product():
    return _product_form(None)


@bp.route("/productos/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id: int):
    row = get_product(get_db(), product_id)
    if row is None:
        abort(404)
    return _product_form(row)


@bp.post("/productos/<int:product_id>/eliminar")
def remove_product(product_id: int):
    connection = get_db()
    if get_product(connection, product_id) is None:
        abort(404)
    filenames = delete_product(connection, product_id)
    connection.commit()
    for filename in filenames:
        remove_file(filename)
    flash("Pieza eliminada.")
    return redirect(url_for("admin.dashboard"))


@bp.get("/pedidos")
def orders():
    view = []
    for order in list_orders(get_db()):
        view.append(
            {
                "id": order["id"],
                "status": order["status"],
                "status_label": STATUS_LABELS.get(order["status"], order["status"]),
                "total_clp": order["total_clp"],
                "customer_name": order["customer_name"],
                "email": order["email"],
                "phone": order["phone"],
                "address": order["address"],
                "city": order["city"],
                "notes": order["notes"],
                "buy_order": order["buy_order"],
                "created_at": order["created_at"],
                "items": order_items(order),
            }
        )
    return render_template("admin/orders.html", orders=view, og=_page("Pedidos", "Pagos de la tienda."))


@bp.get("/importar")
def import_form():
    return render_template("admin/import.html", report=None, og=_page("Importar", "Carga masiva desde Excel."))


@bp.get("/importar/plantilla")
def import_template():
    payload = build_template()
    return send_file(
        BytesIO(payload),
        as_attachment=True,
        download_name="plantilla-productos.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.post("/importar")
def import_submit():
    spreadsheet = request.files.get("planilla")
    if spreadsheet is None or not spreadsheet.filename:
        flash("Sube la planilla Excel.")
        return redirect(url_for("admin.import_form"))
    media_files, file_error = read_uploaded_media(request.files.getlist("archivos"))
    if file_error:
        report = {"file_error": file_error, "rows": [], "created": 0, "skipped": 0, "errors": 0}
    else:
        report = import_workbook(get_db(), spreadsheet.read(), media_files or {})
    return render_template(
        "admin/import.html",
        report=report,
        og=_page("Importar", "Resultado de la carga."),
    )


def _product_form(product):
    connection = get_db()
    media = list_media(connection, product["id"]) if product is not None else []
    if request.method == "GET":
        draft = _draft_from_product(product)
        return _render_product(product, media, draft, [])

    draft, text_errors = _read_text_fields()
    uploads = []
    for storage in request.files.getlist("new_media"):
        if storage and storage.filename:
            uploads.append((storage.filename, storage.read()))
    items, media_errors = arrange_media(
        media,
        request.form.getlist("keep_id"),
        request.form.get("media_order_set") == "1",
        request.form.get("media_order", ""),
        uploads,
    )
    errors = text_errors + media_errors
    if errors:
        return _render_product(product, media, draft, errors)

    saved_names: list[str] = []
    try:
        for item in items:
            if item["source"] == "new":
                item["filename"] = save_bytes(item["data"], item["ext"])
                saved_names.append(item["filename"])
        if product is None:
            product_id = create_product(
                connection,
                name=draft["nombre"],
                description=draft["descripcion"],
                price_clp=draft["precio"],
                category=draft["categoria"],
                stock=draft["stock"],
                active=draft["activo"],
            )
        else:
            product_id = product["id"]
            update_product(
                connection,
                product_id,
                name=draft["nombre"],
                description=draft["descripcion"],
                price_clp=draft["precio"],
                category=draft["categoria"],
                stock=draft["stock"],
                active=draft["activo"],
            )
        replace_media(
            connection,
            product_id,
            [{"filename": item["filename"], "media_type": item["media_type"]} for item in items],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        for filename in saved_names:
            remove_file(filename)
        raise
    kept = {item["filename"] for item in items}
    for row in media:
        if row["filename"] not in kept:
            remove_file(row["filename"])
    flash("Pieza guardada.")
    return redirect(url_for("admin.edit_product", product_id=product_id))


def _render_product(product, media, draft, errors):
    cover = cover_of(media)
    title = "Nueva pieza" if product is None else f"Editar {product['name']}"
    image = ""
    if cover is not None:
        image = url_for("storefront.media_file", filename=cover["filename"], _external=True)
    return render_template(
        "admin/product_form.html",
        product=product,
        media=media,
        draft=draft,
        errors=errors,
        categories=CATEGORIES,
        og=_page(title, "Ficha de la pieza.", image=image),
    )


def _draft_from_product(product) -> dict:
    if product is None:
        return {
            "nombre": "",
            "descripcion": "",
            "precio": "",
            "categoria": CATEGORIES[0],
            "stock": "1",
            "activo": True,
        }
    return {
        "nombre": product["name"],
        "descripcion": product["description"],
        "precio": product["price_clp"],
        "categoria": product["category"],
        "stock": product["stock"],
        "activo": bool(product["active"]),
    }


def _read_text_fields() -> tuple[dict, list[str]]:
    errors = []
    name = request.form.get("nombre", "").strip()
    description = request.form.get("descripcion", "").strip()
    category = request.form.get("categoria", "").strip()
    active = request.form.get("activo") == "1"
    price = None
    stock = None
    try:
        price = parse_price(request.form.get("precio", ""))
    except ValueError as exc:
        errors.append(str(exc))
    try:
        stock = parse_stock(request.form.get("stock", ""))
    except ValueError as exc:
        errors.append(str(exc))
    if not name or len(name) > 80:
        errors.append("El nombre es obligatorio y puede tener hasta 80 caracteres.")
    if not description or len(description) > 2000:
        errors.append("La descripción es obligatoria y puede tener hasta 2000 caracteres.")
    if category not in CATEGORIES:
        errors.append("Elige una categoría.")
    draft = {
        "nombre": name,
        "descripcion": description,
        "precio": price if price is not None else request.form.get("precio", ""),
        "categoria": category or CATEGORIES[0],
        "stock": stock if stock is not None else request.form.get("stock", ""),
        "activo": active,
    }
    return draft, errors


def _password_ok(provided: str) -> bool:
    expected = os.environ.get("ADMIN_PASSWORD", "")
    if not expected or not isinstance(provided, str) or not provided or len(provided) > 200:
        return False
    return hmac.compare_digest(
        hashlib.sha256(provided.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )


def _page(title: str, description: str, image: str = "") -> dict:
    store = os.environ.get("STORE_NAME", "").strip() or "Taller Raíz"
    return {
        "title": f"{title} · {store}",
        "description": description,
        "image": image,
        "type": "website",
        "url": request.url,
    }
