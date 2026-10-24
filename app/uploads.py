"""Image and video checks. Stored names are random; original names are never kept."""

from __future__ import annotations

import os
import re
import secrets

from flask import current_app

IMAGE_MAX_BYTES = 5 * 1024 * 1024
VIDEO_MAX_BYTES = 30 * 1024 * 1024
MAX_IMAGES = 6
STORED_NAME_RE = re.compile(r"^[a-f0-9]{32}\.(jpg|png|webp|mp4|webm)$")

_KIND_BY_EXT = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".mp4": "video",
    ".webm": "video",
}
_STORE_EXT = {
    ".jpg": ".jpg",
    ".jpeg": ".jpg",
    ".png": ".png",
    ".webp": ".webp",
    ".mp4": ".mp4",
    ".webm": ".webm",
}
_MAGIC_BY_EXT = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".webp": "webp",
    ".mp4": "mp4",
    ".webm": "webm",
}


class MediaError(ValueError):
    pass


def classify_upload(filename: str, data: bytes) -> tuple[str, str]:
    """Return (media_type, stored extension) or raise MediaError."""
    if not filename or os.path.basename(filename) != filename or "\x00" in filename:
        raise MediaError("El nombre del archivo no es válido.")
    ext = os.path.splitext(filename)[1].lower()
    kind = _KIND_BY_EXT.get(ext)
    if kind is None:
        raise MediaError("Solo se aceptan imágenes jpg, png o webp, y videos mp4 o webm.")
    if not data:
        raise MediaError("El archivo está vacío.")
    limit = IMAGE_MAX_BYTES if kind == "image" else VIDEO_MAX_BYTES
    if len(data) > limit:
        if kind == "image":
            raise MediaError("Cada imagen puede pesar hasta 5 MB.")
        raise MediaError("El video puede pesar hasta 30 MB.")
    if _sniff(data) != _MAGIC_BY_EXT[ext]:
        raise MediaError("El contenido del archivo no coincide con su extensión.")
    return kind, _STORE_EXT[ext]


def save_bytes(data: bytes, ext: str) -> str:
    filename = secrets.token_hex(16) + ext
    path = os.path.join(current_app.config["MEDIA_FOLDER"], filename)
    with open(path, "wb") as handle:
        handle.write(data)
    return filename


def remove_file(filename: str) -> None:
    if not STORED_NAME_RE.fullmatch(filename or ""):
        return
    path = os.path.join(current_app.config["MEDIA_FOLDER"], filename)
    try:
        os.remove(path)
    except FileNotFoundError:
        return


def arrange_media(existing, keep_ids, order_set: bool, order_raw: str, uploads: list[tuple[str, bytes]]):
    """Build the gallery list. Images stay in the given order; a video is always last.

    existing rows need id, filename and media_type.
    uploads are (original filename, bytes) in the order of n: indexes.
    Returns (items, errors). items have source, filename or data, media_type, ext.
    """
    errors: list[str] = []
    by_id = {str(row["id"]): row for row in existing}
    sequence: list[tuple[str, object, tuple[str, bytes] | None]] = []

    if order_set:
        tokens = [part.strip() for part in order_raw.split(",") if part.strip()]
        used_new: set[int] = set()
        used_existing: set[str] = set()
        for token in tokens:
            kind, sep, ident = token.partition(":")
            if sep != ":" or kind not in {"e", "n"}:
                errors.append("El orden de los archivos no es válido.")
                break
            if kind == "e":
                row = by_id.get(ident)
                if row is None or ident in used_existing:
                    errors.append("Hay un archivo que ya no pertenece a esta pieza.")
                    continue
                used_existing.add(ident)
                sequence.append(("existing", row, None))
            else:
                try:
                    index = int(ident)
                    upload = uploads[index]
                except (ValueError, IndexError):
                    errors.append("Falta uno de los archivos nuevos.")
                    continue
                if index in used_new:
                    errors.append("Un archivo nuevo está repetido.")
                    continue
                used_new.add(index)
                sequence.append(("new", None, upload))
        if not errors and len(used_new) != len(uploads):
            errors.append("La cantidad de archivos nuevos no coincide.")
    else:
        for keep_id in keep_ids:
            row = by_id.get(str(keep_id))
            if row is None:
                errors.append("Hay un archivo que ya no pertenece a esta pieza.")
            else:
                sequence.append(("existing", row, None))
        for upload in uploads:
            sequence.append(("new", None, upload))

    if errors:
        return [], errors

    images = []
    videos = []
    for source, row, upload in sequence:
        if source == "existing":
            item = {
                "source": "existing",
                "filename": row["filename"],
                "media_type": row["media_type"],
            }
            (images if row["media_type"] == "image" else videos).append(item)
            continue
        original, data = upload
        try:
            media_type, ext = classify_upload(original, data)
        except MediaError as exc:
            errors.append(f"{original}: {exc}")
            continue
        item = {
            "source": "new",
            "data": data,
            "ext": ext,
            "media_type": media_type,
            "original": original,
        }
        (images if media_type == "image" else videos).append(item)

    if errors:
        return [], errors
    if len(videos) > 1:
        return [], ["Solo puedes subir un video por pieza."]
    if len(images) > MAX_IMAGES:
        return [], [f"Puedes subir hasta {MAX_IMAGES} imágenes por pieza."]
    if len(images) < 1:
        return [], ["Agrega al menos una imagen. La primera queda como portada."]
    return images + videos, []


def _sniff(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    return None
