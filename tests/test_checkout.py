from app.db import create_order, get_db, get_order_by_buy_order, get_product, set_order_token
from tests.conftest import csrf

WEBPAY_URL = "https://webpay3gint.transbank.cl/webpayserver/initTransaction"


def test_checkout_creates_pending_order_from_database_prices(client, app, add_product, monkeypatch):
    product_id = add_product(price_clp=10000, stock=5)
    token = csrf(client)
    client.post(
        "/carro/agregar",
        data={"csrf_token": token, "product_id": product_id, "quantity": 2},
    )
    with app.app_context():
        get_db().execute("UPDATE products SET price_clp = ? WHERE id = ?", (15000, product_id))
        get_db().commit()

    captured = {}

    def fake_create(buy_order, session_id, amount, return_url):
        captured["amount"] = amount
        captured["buy_order"] = buy_order
        return {"token": "a" * 64, "url": WEBPAY_URL}

    monkeypatch.setattr("app.payments.create_webpay_transaction", fake_create)
    response = client.post(
        "/checkout",
        data={
            "csrf_token": token,
            "nombre": "Ana Pérez",
            "email": "ana@example.com",
            "telefono": "+56912345678",
            "direccion": "Calle Los Aromos 123",
            "ciudad": "Valparaíso",
            "notas": "Dejar en conserjería",
            "precio": "1",
        },
    )
    assert response.status_code == 200
    assert WEBPAY_URL in response.get_data(as_text=True)
    assert captured["amount"] == 30000

    with app.app_context():
        order = get_order_by_buy_order(get_db(), captured["buy_order"])
        assert order["status"] == "pending"
        assert order["total_clp"] == 30000
        assert order["tbk_token"] == "a" * 64
        assert get_product(get_db(), product_id)["stock"] == 5


def test_webpay_return_approves_order_and_decrements_stock(client, app, add_product, monkeypatch):
    product_id = add_product(price_clp=10000, stock=4)
    buy_order = "T123456789abcdef01"
    session_id = "sess-de-prueba"
    token = "b" * 64
    with app.app_context():
        connection = get_db()
        order_id = create_order(
            connection,
            total_clp=10000,
            customer_name="Ana Pérez",
            email="ana@example.com",
            phone="+56912345678",
            address="Calle Los Aromos 123",
            city="Valparaíso",
            notes="",
            items=[
                {
                    "product_id": product_id,
                    "name": "Cartera de prueba",
                    "price_clp": 10000,
                    "quantity": 1,
                    "line_total": 10000,
                }
            ],
            buy_order=buy_order,
            session_id=session_id,
        )
        set_order_token(connection, order_id, token)
        connection.commit()

    def fake_commit(received):
        assert received == token
        return {
            "status": "AUTHORIZED",
            "response_code": 0,
            "buy_order": buy_order,
            "session_id": session_id,
            "amount": 10000,
        }

    monkeypatch.setattr("app.payments.commit_webpay_transaction", fake_commit)
    response = client.post("/pago/retorno", data={"token_ws": token}, follow_redirects=True)
    body = response.get_data(as_text=True)
    assert "Pagado" in body
    assert "Pedido Nº" in body

    with app.app_context():
        order = get_order_by_buy_order(get_db(), buy_order)
        assert order["status"] == "paid"
        assert get_product(get_db(), product_id)["stock"] == 3


def test_webpay_abort_does_not_commit_or_decrement_stock(client, app, add_product, monkeypatch):
    product_id = add_product(price_clp=10000, stock=4)
    buy_order = "Tabcdef01234567890"
    token = "c" * 64
    with app.app_context():
        connection = get_db()
        order_id = create_order(
            connection,
            total_clp=10000,
            customer_name="Ana Pérez",
            email="ana@example.com",
            phone="+56912345678",
            address="Calle Los Aromos 123",
            city="Valparaíso",
            notes="",
            items=[
                {
                    "product_id": product_id,
                    "name": "Cartera de prueba",
                    "price_clp": 10000,
                    "quantity": 1,
                    "line_total": 10000,
                }
            ],
            buy_order=buy_order,
            session_id="sess-abort",
        )
        set_order_token(connection, order_id, token)
        connection.commit()

    def fake_commit(_token):
        raise AssertionError("un pago abortado no se confirma")

    monkeypatch.setattr("app.payments.commit_webpay_transaction", fake_commit)
    response = client.post(
        "/pago/retorno",
        data={"TBK_TOKEN": token, "TBK_ORDEN_COMPRA": buy_order, "TBK_ID_SESION": "sess-abort"},
        follow_redirects=True,
    )
    assert "Rechazado" in response.get_data(as_text=True)
    with app.app_context():
        assert get_order_by_buy_order(get_db(), buy_order)["status"] == "failed"
        assert get_product(get_db(), product_id)["stock"] == 4
