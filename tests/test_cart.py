from app.db import get_db

from tests.conftest import csrf


def test_cart_total_uses_database_price(client, app, add_product):
    product_id = add_product(price_clp=12990, stock=5)
    token = csrf(client)
    added = client.post(
        "/carro/agregar",
        data={"csrf_token": token, "product_id": product_id, "quantity": 2},
    )
    assert added.status_code == 302

    page = client.get("/carro")
    assert b"$25.980" in page.data

    with app.app_context():
        get_db().execute("UPDATE products SET price_clp = ? WHERE id = ?", (10000, product_id))
        get_db().commit()

    updated = client.get("/carro")
    body = updated.get_data(as_text=True)
    assert "$20.000" in body
    assert "$25.980" not in body
