import io

import pytest

from app.db import get_db, list_media
from app.uploads import IMAGE_MAX_BYTES, VIDEO_MAX_BYTES, MediaError, classify_upload
from tests.conftest import jpeg_bytes, png_bytes

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 16
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"


def _product_form(token, files):
    data = {
        "csrf_token": token,
        "nombre": "Bolso de prueba",
        "descripcion": "Cosido a mano con lona y cuero.",
        "precio": "12990",
        "categoria": "Carteras",
        "stock": "3",
        "activo": "1",
        "new_media": files,
    }
    return data


def test_classify_accepts_images_and_video_within_limits():
    media_type, ext = classify_upload("foto.png", png_bytes())
    assert (media_type, ext) == ("image", ".png")
    media_type, ext = classify_upload("foto.jpeg", jpeg_bytes())
    assert (media_type, ext) == ("image", ".jpg")
    assert classify_upload("clip.webm", WEBM) == ("video", ".webm")
    assert classify_upload("clip.mp4", MP4) == ("video", ".mp4")
    exact = b"\xff\xd8\xff" + b"\x00" * (IMAGE_MAX_BYTES - 3)
    assert classify_upload("limite.jpg", exact)[0] == "image"


def test_classify_rejects_bad_type_mismatch_and_size():
    with pytest.raises(MediaError):
        classify_upload("notas.txt", b"hola")
    with pytest.raises(MediaError):
        classify_upload("foto.jpg", png_bytes())
    oversized = b"\xff\xd8\xff" + b"\x00" * IMAGE_MAX_BYTES
    with pytest.raises(MediaError):
        classify_upload("grande.jpg", oversized)
    video = MP4 + b"\x00" * VIDEO_MAX_BYTES
    with pytest.raises(MediaError):
        classify_upload("largo.mp4", video)


def test_admin_upload_rejects_invalid_file_and_stores_valid_media(admin, app):
    client = admin["client"]
    token = admin["token"]
    rejected = client.post(
        "/admin/productos/nuevo",
        data=_product_form(token, (io.BytesIO(b"no-es-imagen"), "notas.txt")),
    )
    assert rejected.status_code == 200
    assert "notas.txt" in rejected.get_data(as_text=True)

    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 0

    saved = client.post(
        "/admin/productos/nuevo",
        data=_product_form(
            token,
            [
                (io.BytesIO(WEBM), "clip.webm"),
                (io.BytesIO(png_bytes()), "mi-foto.png"),
            ],
        ),
    )
    assert saved.status_code == 302

    with app.app_context():
        product = get_db().execute("SELECT id FROM products").fetchone()
        media = list_media(get_db(), product["id"])
        assert [row["media_type"] for row in media] == ["image", "video"]
        assert media[0]["position"] == 0
        assert media[0]["filename"].endswith(".png")
        assert media[0]["filename"] != "mi-foto.png"
        assert media[1]["filename"].endswith(".webm")
        assert media[1]["filename"] != "clip.webm"


def test_admin_upload_rejects_more_than_six_images(admin, app):
    files = [(io.BytesIO(png_bytes()), f"foto-{index}.png") for index in range(7)]
    response = admin["client"].post(
        "/admin/productos/nuevo",
        data=_product_form(admin["token"], files),
    )
    assert response.status_code == 200
    assert "6 imágenes" in response.get_data(as_text=True)
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"] == 0
