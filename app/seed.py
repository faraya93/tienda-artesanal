"""Placeholder catalog so the gallery works before the owner uploads photos."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from io import BytesIO

from flask import current_app
from PIL import Image, ImageDraw, ImageFont

from app.db import SANTIAGO, count_products, create_product, replace_media
from app.uploads import save_bytes

CATALOG = [
    {
        "category": "Carteras",
        "name": "Cartera Huasco",
        "price_clp": 45990,
        "stock": 4,
        "description": (
            "Tejida con lana de oveja del valle del Huasco y forrada en algodón crudo. "
            "El asa es de cuero vegetal curtido en Santiago. "
            "Cada pieza cambia un poco, porque se hace de una en una."
        ),
    },
    {
        "category": "Carteras",
        "name": "Bolso Atacama",
        "price_clp": 38990,
        "stock": 7,
        "description": (
            "Bolso amplio de lona de algodón teñida con cáscara de cebolla y óxido de hierro. "
            "Los refuerzos van cosidos a mano con hilo encerado. "
            "Cabe un cuaderno, la botella y el pan del día."
        ),
    },
    {
        "category": "Carteras",
        "name": "Bandolera Copiapó",
        "price_clp": 32990,
        "stock": 2,
        "description": (
            "Bandolera compacta de cuero y tiras tejidas en telar de peine. "
            "El cierre es un botón de madera de espino. "
            "Sirve para salir con lo justo y las manos libres."
        ),
    },
    {
        "category": "Carteras",
        "name": "Cartera Rari",
        "price_clp": 54990,
        "stock": 9,
        "description": (
            "Inspirada en la crin de Rari: fibra vegetal trenzada sobre una base de lino. "
            "Es liviana, firme y trae un bolsillo interior de algodón. "
            "Hecha a mano en Chile, pieza por pieza."
        ),
    },
    {
        "category": "Carteras",
        "name": "Tote Valparaíso",
        "price_clp": 27990,
        "stock": 5,
        "description": (
            "Tote de lona gruesa con un bolsillo delantero tejido en telar. "
            "Las asas largas dejan el bolso sobre el hombro en la micro o en la feria. "
            "Se lava con cuidado y dura años."
        ),
    },
    {
        "category": "Telares",
        "name": "Tapiz Chiloé",
        "price_clp": 89990,
        "stock": 3,
        "description": (
            "Tapiz de muro con lanas teñidas con plantas del sur: maqui, radal y barba de palo. "
            "El dibujo recuerda los palafitos y el agua quieta. "
            "Se cuelga de una varilla de madera nativa."
        ),
    },
    {
        "category": "Telares",
        "name": "Camino de mesa Pewenche",
        "price_clp": 46990,
        "stock": 6,
        "description": (
            "Camino angosto tejido en telar mapuche, con guarda de rombos en crudo y terracota. "
            "Queda bien sobre una mesa de madera, sin mantel. "
            "El largo alcanza para una mesa de seis."
        ),
    },
    {
        "category": "Telares",
        "name": "Manta de muro Likan",
        "price_clp": 129990,
        "stock": 1,
        "description": (
            "Manta grande para el muro o el respaldo del sillón. "
            "Lana gruesa, nudos visibles y flecos anudados a mano. "
            "Los tonos salen del mismo ovillo, así que no hay dos iguales."
        ),
    },
    {
        "category": "Telares",
        "name": "Funda de cojín Loica",
        "price_clp": 24990,
        "stock": 8,
        "description": (
            "Funda tejida con listas angostas en arena, rojo ladrillo y café. "
            "El cierre es una solapa, sin metal. "
            "Entra un cojín de 40 por 40."
        ),
    },
    {
        "category": "Telares",
        "name": "Paño Llifén",
        "price_clp": 67990,
        "stock": 4,
        "description": (
            "Paño pequeño para la mesa de centro o el velador. "
            "Mezcla lino y lana en un tejido abierto que deja ver la luz. "
            "Los bordes están rematados a mano para que no se deshilachen."
        ),
    },
    {
        "category": "Pulseras",
        "name": "Pulsera de lapislázuli",
        "price_clp": 12990,
        "stock": 18,
        "description": (
            "Cuentas de lapislázuli del norte, con un nudo entre cada una. "
            "El cierre es ajustable, de hilo encerado. "
            "Queda mejor en contacto con la piel."
        ),
    },
    {
        "category": "Pulseras",
        "name": "Pulsera semilla de luma",
        "price_clp": 8990,
        "stock": 12,
        "description": (
            "Semillas pulidas de luma, livianas y oscuras, separadas por mostacillas de vidrio. "
            "El largo se regula con un nudo corredizo. "
            "Hecha a mano en Chile."
        ),
    },
    {
        "category": "Pulseras",
        "name": "Pulsera de cobre martillado",
        "price_clp": 15990,
        "stock": 9,
        "description": (
            "Lámina de cobre martillada a mano y curvada al pulso. "
            "Con los días toma un brillo oscuro que se puede pulir de nuevo. "
            "No sale de un molde: cada curva cambia."
        ),
    },
    {
        "category": "Pulseras",
        "name": "Pulsera de mostacilla Willi",
        "price_clp": 7990,
        "stock": 22,
        "description": (
            "Tejida en telar de mostacillas, con un zigzag angosto en arena y terracota. "
            "El hilo es de nylon encerado para el uso diario. "
            "El cierre es un botón de metal."
        ),
    },
    {
        "category": "Pulseras",
        "name": "Pulsera de plata y lana",
        "price_clp": 18990,
        "stock": 7,
        "description": (
            "Hilo de plata tejido con una hebra de lana teñida. "
            "Se siente tibia y suena muy poco al moverse. "
            "El largo es fijo, pensado para una muñeca mediana."
        ),
    },
    {
        "category": "Otros",
        "name": "Aros de plata quemada",
        "price_clp": 16990,
        "stock": 6,
        "description": (
            "Aros pequeños de plata oxidada, con un punto de cobre. "
            "El gancho es de plata 925. "
            "Son livianos, para usar todo el día."
        ),
    },
    {
        "category": "Otros",
        "name": "Mate de calabaza labrada",
        "price_clp": 22990,
        "stock": 5,
        "description": (
            "Calabaza curada y labrada con un dibujo de hojas. "
            "Viene con una bombilla de alpaca sencilla. "
            "Hay que curarlo la primera vez, como cualquier mate."
        ),
    },
    {
        "category": "Otros",
        "name": "Cuenco de greda de Pomaire",
        "price_clp": 11990,
        "stock": 14,
        "description": (
            "Cuenco torneado en greda de Pomaire y bruñido con piedra. "
            "Sirve para la mesa o para guardar llaves. "
            "No va al horno ni al lavavajillas."
        ),
    },
    {
        "category": "Otros",
        "name": "Colgante de crin de Rari",
        "price_clp": 9990,
        "stock": 3,
        "description": (
            "Figura mínima tejida en crin de caballo, la técnica de Rari. "
            "Cuelga de un cordón de lino. "
            "Es una pieza delicada: mejor lejos del agua."
        ),
    },
    {
        "category": "Otros",
        "name": "Individuales de totora",
        "price_clp": 15990,
        "stock": 0,
        "description": (
            "Par de individuales tejidos en totora del sur. "
            "La fibra es firme y se limpia con un paño apenas húmedo. "
            "El borde está cosido con hilo de algodón. Ahora mismo está agotado."
        ),
    },
]

_PALETTES = (
    ((232, 220, 200), (250, 246, 240), (181, 84, 30)),
    ((243, 230, 212), (250, 246, 240), (140, 74, 47)),
    ((226, 206, 184), (247, 239, 228), (110, 59, 42)),
    ((236, 214, 196), (250, 246, 240), (181, 84, 30)),
)
_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/Library/Fonts/Georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
)


def seed_if_empty() -> int:
    """Load the sample catalog once. A second process waits on the SQLite lock."""
    from app.db import get_db

    connection = get_db()
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    try:
        existing = count_products(connection)
        if existing:
            connection.commit()
            return existing
        base = datetime.now(SANTIAGO)
        for index, item in enumerate(CATALOG):
            created_at = (base - timedelta(minutes=index)).isoformat(timespec="minutes")
            product_id = create_product(
                connection,
                name=item["name"],
                description=item["description"],
                price_clp=item["price_clp"],
                category=item["category"],
                stock=item["stock"],
                active=1,
                created_at=created_at,
            )
            image_count = 2 + (index % 2)
            media = []
            for variant in range(image_count):
                payload = _placeholder(
                    item["name"],
                    item["category"],
                    (index + variant) % len(_PALETTES),
                    variant,
                )
                filename = save_bytes(payload, ".jpg")
                media.append({"filename": filename, "media_type": "image"})
            replace_media(connection, product_id, media)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    total = count_products(connection)
    current_app.logger.info("Catálogo de ejemplo cargado: %s productos", total)
    return total


def _placeholder(name: str, category: str, palette_index: int, variant: int) -> bytes:
    width, height = 800, 1000
    top, bottom, accent = _PALETTES[palette_index]
    column = Image.new("RGB", (1, height))
    pixels = column.load()
    for y in range(height):
        blend = y / (height - 1)
        pixels[0, y] = tuple(int(a + (b - a) * blend) for a, b in zip(top, bottom))
    image = column.resize((width, height))
    draw = ImageDraw.Draw(image)
    circle_x = 140 + variant * 180
    draw.ellipse((circle_x, 180, circle_x + 220, 400), fill=accent)
    draw.rectangle((0, int(height * 0.78), width, height), fill=accent)
    title_font = _font(54)
    small_font = _font(28)
    lines = _wrap(draw, name, title_font, width - 120)
    y = 460
    for line in lines:
        draw.text((60, y), line, font=title_font, fill=(62, 42, 32))
        y += 68
    draw.text((60, height - 150), category.upper(), font=small_font, fill=(250, 246, 240))
    label = "HECHO A MANO" if variant == 0 else f"DETALLE {variant + 1}"
    draw.text((60, height - 100), label, font=small_font, fill=(250, 246, 240))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=82, optimize=True)
    return buffer.getvalue()


def _font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]
