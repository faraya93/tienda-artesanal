# Taller Raíz

Tienda server-rendered para piezas hechas a mano en Chile (carteras, telares, pulseras). El catálogo, el carro y los pedidos viven en SQLite. El pago lo hace Webpay Plus; la tienda no ve ni guarda datos de tarjeta. No hay cuentas de clientes.

## Requisitos

Python 3.13 o superior, con Flask, Jinja2, SQLite, el SDK oficial `transbank-sdk`, `openpyxl` y Pillow. No hay frontend de build: un CSS y dos archivos de JavaScript vainilla (`static/gallery.js` para la ficha, `static/admin.js` para ordenar fotos).

Este proyecto se escribió para 3.13 y se verificó con el intérprete disponible en esta máquina (Python 3.15).

## Cómo correrla

Desde la raíz del proyecto:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env`: cambia `FLASK_SECRET_KEY` y `ADMIN_PASSWORD`. El resto del ejemplo ya trae el nombre de la tienda y las credenciales públicas de integración de Transbank.

```bash
flask run
```

Abre http://127.0.0.1:5000 . Si la base está vacía, el arranque carga 20 piezas de ejemplo con fotos de relleno (degradados terracota/arena, no imágenes generadas por IA). Para repetir esa carga, borra la carpeta `instance/` y vuelve a arrancar. También puedes correr `flask seed` cuando no hay productos.

Pruebas:

```bash
pytest
```

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `FLASK_SECRET_KEY` | Firma la sesión. Obligatoria. |
| `STORE_NAME` | Nombre visible. Si falta, se usa «Taller Raíz». |
| `ADMIN_PASSWORD` | Única clave de `/admin`. Se compara en tiempo constante. |
| `META_PIXEL_ID` | Si son 5 a 20 dígitos, cada página incluye el píxel de Meta. Vacío = no se incluye. |
| `TRANSBANK_COMMERCE_CODE` | Código de comercio Webpay Plus. |
| `TRANSBANK_API_KEY` | Llave del mismo ambiente. |
| `TRANSBANK_ENVIRONMENT` | `integration` (por defecto) o `production`. También acepta `test`, `integracion`, `live` y `produccion`. Cualquier otro valor es un error. |

Las credenciales del `.env.example` son las de integración que publica el SDK (`597055555532` y la API key de `IntegrationApiKeys.WEBPAY`). No sirven en producción.

## Tienda

- Inicio con el nombre, la bajada «Hecho a mano en Chile» y filtro por categoría.
- Ficha con galería: la foto de posición 0 es la portada; el video, si existe, va al final (`muted`, `loop`, `playsinline`, `controls`).
- Carro en la sesión de Flask. No hay cuentas.
- El total se calcula en el servidor con el precio de la base, al mostrar el carro y al crear el pedido. Un precio enviado por el navegador se ignora.
- Los precios son enteros en pesos y se muestran como `$12.990`.
- Checkout de invitado: nombre, correo, teléfono, dirección, ciudad y notas. El envío no se cobra aquí; la dirección queda para coordinarlo después.

### Probar un pago en integración

Webpay devuelve el navegador a `http://127.0.0.1:5000/pago/retorno`. En integración ese retorno lo hace el browser, así que localhost alcanza. No hace falta un servidor público.

Tarjeta de prueba publicada por Transbank:

- VISA `4051885600446623`
- CVV `123`
- Vencimiento cualquiera a futuro
- RUT `11.111.111-1`
- Clave `123`

Un pago aprobado queda `paid` y descuenta stock (nunca bajo 0). Un rechazo o un aborto queda `failed` y no descuenta. Si la persona no vuelve de Webpay, el pedido sigue `pending`. La confirmación usa la referencia `buy_order`, no el id correlativo.

La URL de redirección tiene que ser `https` y el host de Webpay del ambiente (`webpay3gint.transbank.cl` o `webpay3g.transbank.cl`).

## Administración

`/admin` pide la clave de `ADMIN_PASSWORD` y la guarda en la sesión. Sin sesión, cualquier ruta `/admin` vuelve al login.

Desde ahí se crean y editan piezas (nombre, descripción, precio, categoría, stock, visible, hasta 6 fotos y 1 video). La primera foto es la portada; se cambia arrastrándola al inicio. El video se guarda y se muestra al final. Los archivos se guardan con nombre aleatorio.

Los pedidos muestran estado Pendiente, Pagado o Rechazado.

## Contrato de importación Excel

Esta es la interfaz que debe producir una herramienta externa. No hay API HTTP: se sube el `.xlsx` y los archivos en `/admin/importar`.

Hoja activa, primera fila exactamente:

`nombre`, `descripcion`, `precio`, `categoria`, `stock`, `imagenes`, `video`

| Columna | Regla |
| --- | --- |
| `nombre` | Obligatorio, hasta 80 caracteres. |
| `descripcion` | Obligatoria, hasta 2000 caracteres. |
| `precio` | Entero en pesos, de 1 a 50.000.000. En Excel escribe `12990`, no `12.990`: Excel puede guardar eso como decimal y la fila se rechaza. También se acepta el texto `12.990` y un float entero (`45990.0`). |
| `categoria` | Exacto: `Carteras`, `Telares`, `Pulseras` u `Otros`. |
| `stock` | Entero de 0 a 100.000. |
| `imagenes` | Uno a seis nombres de archivo separados por coma. El primero es la portada. Deben ir en el mismo envío. |
| `video` | Opcional. Un `mp4` o `webm`. Queda al final de la galería. |

La planilla de descarga trae una fila de ejemplo. Hay que reemplazarla: si se importa tal cual, falla porque `foto1.jpg` y `foto2.jpg` no vienen en el envío.

Los nombres se comparan sin distinguir mayúsculas, solo el nombre del archivo (sin carpetas). Si dos archivos del envío se llaman igual, no se importa nada. El mismo nombre puede usarse en varias filas; cada pieza recibe su propia copia.

Fotos: jpg, png o webp, hasta 5 MB. Video: mp4 o webm, hasta 30 MB. El contenido tiene que coincidir con la extensión.

Cada fila se valida sola. Una fila vacía queda **omitida**. Una fila inválida queda en **error** y no se crea. Las filas válidas del mismo archivo sí se crean. El tope es 500 filas de datos. El informe muestra fila, nombre, resultado y detalle.

Si el navegador ofrece reenviar el formulario al recargar, hay que cancelar: si no, las piezas creadas se duplican.

## Decisiones

- CSRF con un token de sesión en cada POST. Se eligió a mano, sin Flask-WTF. El retorno de Webpay no lleva ese token: Transbank llama desde otro sitio. Esa ruta solo acepta un `token_ws` que ya está en un pedido y lo confirma con el SDK. Si llegan `TBK_TOKEN` o solo `TBK_ORDEN_COMPRA`, el pago se marca rechazado y no se confirma.
- Hace falta al menos una imagen por pieza para que la grilla tenga portada.
- El stock se revisa al armar el pedido y se descuenta solo si Webpay autoriza. Si el stock llegó a 0 mientras tanto, el pago igual queda pagado y el stock se queda en 0.
- No hay paginación: el inicio muestra todas las piezas activas.
- No hay costo de envío ni cuentas de usuario.
- `og:image` en la ficha es la portada. En el resto de las páginas, si no hay una portada propia, se usa la primera portada del catálogo.
- La URL pública del pedido es la `buy_order`, no el id.
- Los datos de tarjeta, el número enmascarado y el código de autorización no se escriben en SQLite.

## Fuera de alcance

Cuentas de usuario, cálculo de envío, certificación de producción de Transbank, deploy, cupones y generación de imágenes con IA.
