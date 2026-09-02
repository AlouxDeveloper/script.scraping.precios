import os
import csv
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd
from curl_cffi import requests
from curl_cffi.requests.errors import RequestsError

# === Configuración de Archivos y Rutas ===
EXCEL_INPUT = "./data/url_catego_isseg.xlsx"
CSV_OUTPUT = "./salida/data/2026/09_septiembre/scraping_detalle_isseg.csv"
NOMBRE_COLUMNA_URL_ENTRADA = "Url"
TIENDA_NOMBRE = "17"

BASE_URL_PRODUCTO = "https://farmaciasisseg.com.mx/producto/"

# Cabeceras completas que espera el backend/WAF de ISSEG
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
    "Origin": "https://farmaciasisseg.com.mx",
    "Referer": "https://farmaciasisseg.com.mx/",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

# Columnas de salida FINAL
FIELDNAMES = [
    "SKU",
    "URL_PRODUCTO",
    "PRODUCTO",
    "PRECIO_ACTUAL",
    "PRECIO_OFERTA",
    "URL_IMAGEN",
    "FECHA",
    "TIENDA",
]


# === Utilidades de Formato ===
def _fmt_price(val: Optional[float]) -> str:
    """Formatea float a '1,234.56'. Si None o inválido, devuelve ''."""
    if val is None:
        return ""
    try:
        return "{:,.2f}".format(float(val))
    except Exception:
        return str(val)


def transformar_producto(producto: Dict[str, Any]) -> Dict[str, str]:
    """Mapea los datos del producto devuelto por la API al esquema final."""
    codigo_barras = str(producto.get("codigoBarras", "")).strip()
    url_producto_final = f"{BASE_URL_PRODUCTO}{codigo_barras}"

    precio_actual = producto.get("precioOriginal")
    precio_oferta = producto.get("precioPublico")

    imagen_data = producto.get("nombre", "")
    url_imagen_final = f"data:image/png;base64,{imagen_data}" if imagen_data else ""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "SKU": codigo_barras,
        "URL_PRODUCTO": url_producto_final,
        "PRODUCTO": str(producto.get("descripcionCorta", "")).strip(),
        "PRECIO_ACTUAL": _fmt_price(precio_actual),
        "PRECIO_OFERTA": _fmt_price(precio_oferta),
        "URL_IMAGEN": url_imagen_final,
        "FECHA": timestamp,
        "TIENDA": TIENDA_NOMBRE,
    }


# === Función de Extracción y Guardado ===
def extraer_productos_de_categoria_y_guardar(
    session: requests.Session,
    url_api: str,
    es_primera_escritura_global: bool,
    max_retries: int = 3,
) -> int:
    """Consulta la API de la categoría con reintentos y vuelca productos únicos al CSV."""
    print(f"\n🚀 Iniciando extracción para URL de categoría: **{url_api}**")

    datos = None
    for intento in range(1, max_retries + 1):
        try:
            respuesta = session.get(url_api, timeout=20)

            if respuesta.status_code == 200:
                datos = respuesta.json()
                break
            elif respuesta.status_code == 468:
                print(f"  ⚠️ Error HTTP 468 (WAF) en intento {intento}/{max_retries}. Esperando...")
                time.sleep(3 * intento)
            else:
                print(f"  ❌ Error HTTP {respuesta.status_code} al acceder a la API: {url_api}")
                return 0

        except RequestsError as e:
            print(f"  ⚠️ Error de red/timeout en intento {intento}/{max_retries}: {e}")
            time.sleep(2 * intento)
        except Exception as e:
            print(f"  ❌ Error inesperado al procesar la URL {url_api}: {e}")
            return 0

    if datos is None:
        print(f"  ❌ No se pudo obtener respuesta válida tras {max_retries} intentos: {url_api}")
        return 0

    if not isinstance(datos, list):
        print("  ⚠️ Advertencia: La respuesta de la API no es una lista de productos. Omitiendo.")
        return 0

    # 1. Transformar productos
    productos_a_guardar = [transformar_producto(p) for p in datos if isinstance(p, dict)]

    # 2. Control de duplicados consultando el progreso previo
    procesados = set()
    if os.path.exists(CSV_OUTPUT) and os.stat(CSV_OUTPUT).st_size > 0:
        try:
            prev = pd.read_csv(CSV_OUTPUT, sep=",", encoding="utf-8", dtype={"SKU": str})
            procesados = set(prev["SKU"].dropna().tolist())
        except Exception as e:
            print(f"  ⚠️ Error al leer progreso de CSV: {e}. Se añadirá sin deduplicar lote previo.")

    productos_unicos = [
        prod for prod in productos_a_guardar if prod["SKU"] and prod["SKU"] not in procesados
    ]

    # 3. Guardado en disco en tiempo real
    if productos_unicos:
        # Si el archivo no existe o está vacío, requiere encabezado
        requiere_encabezado = es_primera_escritura_global and (
            not os.path.exists(CSV_OUTPUT) or os.stat(CSV_OUTPUT).st_size == 0
        )

        with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES, delimiter=",")
            if requiere_encabezado:
                writer.writeheader()

            for row in productos_unicos:
                writer.writerow(row)
            output_file.flush()

        print(f"  💾 Productos únicos añadidos: {len(productos_unicos)}.")
        return len(productos_unicos)

    print("  ✅ Todos los productos de esta categoría ya estaban procesados.")
    return 0


# === Función Principal ===
def main():
    if not os.path.exists(EXCEL_INPUT):
        print(f"Error: No se encontró el archivo de entrada '{EXCEL_INPUT}'.")
        return

    try:
        df_categorias = pd.read_excel(EXCEL_INPUT)
        urls_categorias = df_categorias[NOMBRE_COLUMNA_URL_ENTRADA].dropna().unique().tolist()
    except KeyError:
        print(f"Error: El archivo '{EXCEL_INPUT}' no tiene la columna '{NOMBRE_COLUMNA_URL_ENTRADA}'.")
        return
    except Exception as e:
        print(f"Error al leer el archivo Excel: {e}")
        return

    # Crear directorio de salida si no existe
    output_dir = os.path.dirname(CSV_OUTPUT)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    print(f"Se encontraron **{len(urls_categorias)}** URLs de categorías para procesar.")

    # Inicializar sesión persistente impersonando Chrome
    session = requests.Session(impersonate="chrome120")
    session.headers.update(HEADERS)

    # Handshake previo opcional al portal principal para recibir cookies iniciales
    try:
        session.get("https://farmaciasisseg.com.mx/", timeout=10)
    except Exception:
        pass

    total_productos_extraidos = 0
    es_primera_escritura = not os.path.exists(CSV_OUTPUT) or os.stat(CSV_OUTPUT).st_size == 0

    for i, url_categoria in enumerate(urls_categorias):
        print(f"\n--- Procesando Categoría {i + 1} de {len(urls_categorias)} ---")

        productos_categoria = extraer_productos_de_categoria_y_guardar(
            session=session,
            url_api=url_categoria,
            es_primera_escritura_global=es_primera_escritura,
        )

        total_productos_extraidos += productos_categoria

        if productos_categoria > 0:
            es_primera_escritura = False

        print(f"  Total acumulado de productos: **{total_productos_extraidos}**.")
        time.sleep(1.5)

    if total_productos_extraidos > 0:
        print(
            f"\n🎉 ¡Proceso finalizado! Se extrajeron un total de **{total_productos_extraidos}** "
            f"productos y se guardaron en **'{CSV_OUTPUT}'**."
        )
    else:
        print("\n⚠️ El proceso finalizó sin nuevos productos extraídos.")


if __name__ == "__main__":
    main()