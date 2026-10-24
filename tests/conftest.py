import io

import pytest
from PIL import Image

from app import create_app
from app.db import create_product, get_db


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("STORE_NAME", "Taller Test")
    monkeypatch.setenv("ADMIN_PASSWORD", "clave-segura")
    monkeypatch.setenv("TRANSBANK_COMMERCE_CODE", "597055555532")
    monkeypatch.setenv("TRANSBANK_API_KEY", "test-api-key")
    monkeypatch.setenv("TRANSBANK_ENVIRONMENT", "integration")
    monkeypatch.delenv("META_PIXEL_ID", raising=False)
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "DATABASE": str(tmp_path / "test.sqlite"),
            "MEDIA_FOLDER": str(tmp_path / "media"),
            "PROPAGATE_EXCEPTIONS": True,
        }
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, path="/"):
    client.get(path)
    with client.session_transaction() as sess:
        return sess["csrf_token"]


@pytest.fixture
def admin(client):
    token = csrf(client, "/admin/login")
    response = client.post(
        "/admin/login",
        data={"csrf_token": token, "password": "clave-segura"},
    )
    assert response.status_code == 302
    with client.session_transaction() as sess:
        return {"client": client, "token": sess["csrf_token"]}


@pytest.fixture
def add_product(app):
    def _add(**overrides):
        fields = {
            "name": "Cartera de prueba",
            "description": "Hecha a mano en el taller, con lana y algodón.",
            "price_clp": 10000,
            "category": "Carteras",
            "stock": 5,
            "active": 1,
        }
        fields.update(overrides)
        with app.app_context():
            connection = get_db()
            product_id = create_product(connection, **fields)
            connection.commit()
            return product_id

    return _add


def png_bytes(color=(181, 84, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (232, 220, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()
