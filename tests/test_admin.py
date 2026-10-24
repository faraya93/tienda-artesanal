def test_admin_redirects_when_logged_out(client):
    response = client.get("/admin")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")


def test_login_rejects_wrong_password(client):
    client.get("/admin/login")
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    response = client.post(
        "/admin/login",
        data={"csrf_token": token, "password": "no-es-la-clave"},
    )
    assert response.status_code == 200
    assert "Clave incorrecta" in response.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert sess.get("is_admin") is not True


def test_pixel_snippet_only_when_configured(client, monkeypatch):
    monkeypatch.setenv("META_PIXEL_ID", "1234567890")
    html = client.get("/").get_data(as_text=True)
    assert "fbq('init', '1234567890')" in html
    monkeypatch.setenv("META_PIXEL_ID", "")
    html = client.get("/").get_data(as_text=True)
    assert "fbq(" not in html
