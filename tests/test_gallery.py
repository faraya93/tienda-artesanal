from app.db import cover_of, get_db, list_media


def test_gallery_is_ordered_and_cover_is_position_zero(client, app, add_product):
    product_id = add_product()
    files = {
        0: "a" * 32 + ".jpg",
        1: "b" * 32 + ".jpg",
        2: "c" * 32 + ".png",
        3: "d" * 32 + ".mp4",
    }
    with app.app_context():
        connection = get_db()
        for position in (2, 0, 1, 3):
            media_type = "video" if position == 3 else "image"
            connection.execute(
                """
                INSERT INTO media (product_id, filename, media_type, position)
                VALUES (?, ?, ?, ?)
                """,
                (product_id, files[position], media_type, position),
            )
        connection.commit()
        media = list_media(connection, product_id)
        assert [row["position"] for row in media] == [0, 1, 2, 3]
        assert cover_of(media)["filename"] == files[0]
        assert cover_of(media)["position"] == 0

    html = client.get(f"/producto/{product_id}").get_data(as_text=True)
    gallery = html.split('data-gallery', 1)[1]
    assert gallery.find(files[0]) < gallery.find(files[1]) < gallery.find(files[2]) < gallery.find(files[3])
    assert 'data-cover="true"' in gallery
    assert gallery.find('data-cover="true"') < gallery.find(files[1])
    video = gallery[gallery.find("<video"): gallery.find("</video>")]
    for attribute in ("muted", "loop", "playsinline", "controls"):
        assert attribute in video
