"""Detalle de precios de HEB (tienda 12, fase 2).

Lee las URLs de producto que dejó la fase 1 y consulta el API JSON interno
del sitio, en vez de abrir cada ficha con un navegador.

    uv run --project extract extract/detalle/scraping_detalle_heb.py

Correr siempre desde la raíz del repo: las rutas son relativas a ella.
"""

# ===========================================================================
# Versión anterior (Selenium + selectores VTEX), conservada como referencia.
# Dejó de capturar en septiembre de 2026 por dos cambios de la tienda:
#
#   1. HEB migró de VTEX a un front propio en Next.js, así que las clases
#      `vtex-store-components-3-x-*` que buscaba este código desaparecieron
#      del HTML y toda URL terminaba en "sin datos extraídos".
#   2. HEB puso Imperva delante del dominio, que detecta al navegador
#      automatizado y responde "Access denied / Error 15". El bloqueo es al
#      navegador, no a la IP: una petición normal desde la misma red
#      responde 200.
#
# Por eso la versión vigente no camufla el navegador: lo quita.
# ===========================================================================
#
# import os
# import csv
# import time
# import random
# import re
# import pandas as pd
# from datetime import datetime
# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait as WW
# from selenium.webdriver.support import expected_conditions as EC
# from webdriver_manager.chrome import ChromeDriverManager
# from tqdm import tqdm
#
# # === Configuración ===
# CSV_INPUT    = "./salida/urls/urls_scraping_heb.csv"
# CSV_OUTPUT   = "./salida/data/2026/09_septiembre/scraping_detalle_heb.csv"
# TIENDA       = "12"
# # CSV aparte para URLs que fallaron, para no repetirlas al reanudar.
# CSV_ESTADO_URLS = "./salida/data/2026/09_septiembre/scraping_detalle_heb_fallidas.csv"
# # Version de Chrome que se declara en el User-Agent; ajusta aqui si cambia.
# CHROME_VERSION = 153
#
#
# def marcar_fallida(url: str, detalle: str = "") -> None:
#     """Registra una URL que no se pudo procesar en CSV_ESTADO_URLS."""
#     es_nuevo = not os.path.exists(CSV_ESTADO_URLS) or os.stat(CSV_ESTADO_URLS).st_size == 0
#     with open(CSV_ESTADO_URLS, "a", newline="", encoding="utf-8") as f:
#         w = csv.writer(f)
#         if es_nuevo:
#             w.writerow(["URL_PRODUCTO", "Estatus", "Detalle", "Fecha_Hora_Captura"])
#         w.writerow([url, "ERROR", detalle, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
#
#
# def cargar_procesados():
#     """Une URLs exitosas (CSV_OUTPUT) y fallidas (CSV_ESTADO_URLS)."""
#     procesados = set()
#     if os.path.exists(CSV_OUTPUT) and os.path.getsize(CSV_OUTPUT) > 0:
#         try:
#             procesados |= set(pd.read_csv(CSV_OUTPUT)["URL_PRODUCTO"].tolist())
#         except:
#             pass
#     if os.path.exists(CSV_ESTADO_URLS) and os.path.getsize(CSV_ESTADO_URLS) > 0:
#         try:
#             procesados |= set(pd.read_csv(CSV_ESTADO_URLS)["URL_PRODUCTO"].tolist())
#         except:
#             pass
#     return procesados
#
# def configurar_driver():
#     print("🌐 Iniciando nueva sesión del navegador...")
#     opts = Options()
#     opts.add_argument("--start-maximized")
#     opts.add_argument("--disable-blink-features=AutomationControlled")
#     # En Mac, a veces ayuda desactivar la aceleración de hardware para evitar crashes
#     opts.add_argument("--disable-gpu")
#     opts.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36")
#     service = Service(ChromeDriverManager().install())
#     driver = webdriver.Chrome(service=service, options=opts)
#     driver.set_page_load_timeout(30) # Evita que se quede colgado infinitamente
#     return driver
#
# def clean_price(txt: str) -> str:
#     if not txt: return "0.00"
#     t = txt.replace(",", "").replace("$", "").strip()
#     m = re.search(r"(\d+(?:\.\d{1,2})?)", t)
#     return m.group(1) if m else "0.00"
#
# def extraer_datos_pdp(driver, url):
#     try:
#         driver.get(url)
#         wait = WW(driver, 20)
#
#         # Esperar a que el nombre sea visible
#         wait.until(EC.presence_of_element_located((By.CLASS_NAME, "vtex-store-components-3-x-productBrand")))
#         time.sleep(2)
#
#         # 1. Nombre e Identificadores
#         nombre = driver.find_element(By.CLASS_NAME, "vtex-store-components-3-x-productBrand").text.strip()
#         sku_raw = driver.find_element(By.CLASS_NAME, "vtex-product-identifier-0-x-product-identifier__value").text.strip()
#         sku_limpio = sku_raw.replace("MXYZ_", "").strip()
#
#         # 2. Precios
#         try:
#             p_actual_raw = driver.find_element(By.CLASS_NAME, "vtex-product-price-1-x-listPriceValue").text
#             precio_actual = clean_price(p_actual_raw)
#         except:
#             precio_actual = "0.00"
#
#         try:
#             p_oferta_raw = driver.find_element(By.CLASS_NAME, "price").text
#             precio_oferta = clean_price(p_oferta_raw)
#         except:
#             precio_oferta = "0.00"
#
#         # --- Lógica de Respaldo de Precios ---
#         if precio_actual == "0.00": precio_actual = precio_oferta
#         if precio_oferta == "0.00": precio_oferta = precio_actual
#
#         # 3. Imagen
#         try:
#             img_el = driver.find_element(By.CSS_SELECTOR, ".vtex-store-components-3-x-productImageTag, img[itemprop='image']")
#             url_imagen = img_el.get_attribute("src")
#         except:
#             url_imagen = ""
#
#         return {
#             "SKU": sku_limpio,
#             "Producto": nombre,
#             "Precio_Actual": precio_actual,
#             "Precio_Oferta": precio_oferta,
#             "URL_IMAGEN": url_imagen
#         }
#     except Exception as e:
#         # Si el error es de conexión o el navegador se cerró, lanzamos la excepción para reiniciar
#         if "session" in str(e).lower() or "unreachable" in str(e).lower():
#             raise e
#         print(f"      ⚠️ No se pudo extraer datos (posible producto agotado o error de carga)")
#         return None
#
# def main():
#     if not os.path.exists(CSV_INPUT):
#         print(f"❌ No existe: {CSV_INPUT}"); return
#
#     df_urls = pd.read_csv(CSV_INPUT)
#     os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
#
#     driver = configurar_driver()
#     barra = tqdm(total=len(df_urls), desc="heb", unit="url", initial=len(cargar_procesados()))
#
#     try:
#         idx = 0
#         while idx < len(df_urls):
#             # Recargar lista de procesados en cada iteración por seguridad
#             procesados = cargar_procesados()
#
#             row = df_urls.iloc[idx]
#             url = row["URL_PRODUCTO"]
#
#             if url in procesados:
#                 idx += 1
#                 barra.update(1)
#                 continue
#
#             print(f"🔎 [{idx+1}/{len(df_urls)}] {url}")
#
#             try:
#                 datos = extraer_datos_pdp(driver, url)
#                 if datos:
#                     file_exists = os.path.exists(CSV_OUTPUT)
#                     with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
#                         writer = csv.DictWriter(f, fieldnames=["SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda"])
#                         if not file_exists: writer.writeheader()
#
#                         writer.writerow({
#                             "SKU": datos["SKU"],
#                             "URL_PRODUCTO": url,
#                             "Producto": datos["Producto"],
#                             "Precio_Actual": datos["Precio_Actual"],
#                             "Precio_Oferta": datos["Precio_Oferta"],
#                             "URL_IMAGEN": datos["URL_IMAGEN"],
#                             "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#                             "Tienda": TIENDA
#                         })
#                     print(f"   ✅ Guardado: ${datos['Precio_Oferta']}")
#                 else:
#                     marcar_fallida(url, "sin datos extraídos")
#
#                 idx += 1 # Solo avanzamos si no hubo error de sesión
#                 barra.update(1)
#                 time.sleep(random.uniform(1.5, 3.0))
#
#             except Exception as e:
#                 print(f"   💥 Error de sesión detectado: {str(e)[:50]}")
#                 print("   🔄 Reiniciando navegador y reintentando producto actual...")
#                 try: driver.quit()
#                 except: pass
#                 time.sleep(5)
#                 driver = configurar_driver()
#                 # No incrementamos idx para que reintente el mismo producto
#
#     finally:
#         try: driver.quit()
#         except: pass
#         barra.close()
#         print(f"\n🎯 Proceso finalizado.")
#
# if __name__ == "__main__":
#     main()

# ===========================================================================
# Versión vigente: API JSON interno de HEB, sin navegador.
# ===========================================================================

import csv
import os
import random
import re
import time
from datetime import datetime

import pandas as pd
import requests
from tqdm import tqdm

# === Configuración ===
CSV_INPUT = "./salida/urls/urls_scraping_heb.csv"
CSV_OUTPUT = "./salida/data/2026/09_septiembre/scraping_detalle_heb.csv"
TIENDA = "12"
# CSV aparte para URLs que fallaron, para no repetirlas al reanudar.
CSV_ESTADO_URLS = (
    "./salida/data/2026/09_septiembre/scraping_detalle_heb_fallidas.csv"
)
# Version de Chrome que se declara en el User-Agent; ajusta aqui si cambia.
CHROME_VERSION = 153

# Endpoints que el propio front de HEB consulta por XHR al abrir una ficha.
# Responden JSON sin sesion ni cookies. BUSQUEDA es el respaldo: entrega el
# mismo objeto dentro de "products" cuando by-ref contesta vacio.
API_PRODUCTO = "https://www.heb.com.mx/api/product/by-ref/{ref}"
API_BUSQUEDA = "https://www.heb.com.mx/api/search"
# Sucursal que el sitio sirve cuando no hay una elegida, la misma que veia la
# version con Selenium. Se fija explicita porque HEB cambia precio y stock
# segun la sucursal, y el historico solo es comparable si no se mueve.
STORE_ID = "hebmx002907"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{CHROME_VERSION}.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-MX,es;q=0.9",
    "Referer": "https://www.heb.com.mx/",
}

FIELDNAMES = [
    "SKU", "URL_PRODUCTO", "Producto", "Precio_Actual",
    "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda",
]

REINTENTOS = 3
PAUSA_ENTRE_PRODUCTOS = (0.4, 0.9)
# Imperva sigue delante del dominio. Si empieza a devolver su pagina de
# bloqueo en vez de JSON se corta la corrida, porque marcar miles de URLs
# como fallidas las dejaria saltadas al reanudar sin haberlas intentado.
MAX_BLOQUEOS_SEGUIDOS = 10


class BloqueoWAF(Exception):
    """El dominio respondió con la página de bloqueo de Imperva."""


def marcar_fallida(url: str, detalle: str = "") -> None:
    """Registra una URL que no se pudo procesar en CSV_ESTADO_URLS."""
    es_nuevo = (
        not os.path.exists(CSV_ESTADO_URLS)
        or os.stat(CSV_ESTADO_URLS).st_size == 0
    )
    with open(CSV_ESTADO_URLS, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if es_nuevo:
            w.writerow(
                ["URL_PRODUCTO", "Estatus", "Detalle", "Fecha_Hora_Captura"]
            )
        w.writerow(
            [url, "ERROR", detalle,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        )


def cargar_procesados() -> set:
    """Une URLs exitosas (CSV_OUTPUT) y fallidas (CSV_ESTADO_URLS)."""
    procesados = set()
    if os.path.exists(CSV_OUTPUT) and os.path.getsize(CSV_OUTPUT) > 0:
        try:
            df_previo = pd.read_csv(CSV_OUTPUT)
            procesados |= set(
                df_previo["URL_PRODUCTO"].dropna().astype(str).tolist()
            )
        except Exception as e:
            print(f"⚠️ Alerta leyendo avance previo: {e}")
    if os.path.exists(CSV_ESTADO_URLS) and os.path.getsize(CSV_ESTADO_URLS) > 0:
        try:
            df_fallidas = pd.read_csv(CSV_ESTADO_URLS)
            procesados |= set(
                df_fallidas["URL_PRODUCTO"].dropna().astype(str).tolist()
            )
        except Exception as e:
            print(f"⚠️ Alerta leyendo URLs fallidas previas: {e}")
    return procesados


def obtener_ref(sku, url: str) -> str:
    """Devuelve el refId del producto: la columna SKU o el final de la URL.

    El CSV de la fase 1 ya trae el SKU, que en HEB es el mismo refId que
    espera el API. El respaldo lee el número con el que cierra la URL
    (.../heb-cubrebocas-desechable-plisado-adulto-azul-50-pi-50-pz-897744/p).
    """
    ref = str(sku).strip()
    if ref and ref.lower() != "nan":
        return ref
    coincidencia = re.search(r"-(\d+)/p", url)
    return coincidencia.group(1) if coincidencia else ""


def _json_o_bloqueo(respuesta) -> dict:
    """Devuelve el JSON de la respuesta; distingue bloqueo de fallo puntual.

    Un fallo puntual se reintenta; un bloqueo del WAF corta la corrida, así
    que se separan aquí en vez de dejar que ambos se vean igual.
    """
    if "json" not in respuesta.headers.get("Content-Type", ""):
        cuerpo = respuesta.text[:2000]
        if "Incapsula" in cuerpo or "Access denied" in cuerpo:
            raise BloqueoWAF("Imperva devolvió su página de bloqueo")
        return {}
    try:
        datos = respuesta.json()
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}


def consultar_producto(sesion: requests.Session, ref: str) -> dict:
    """Pide el producto al API con reintentos; devuelve {} si no hubo datos.

    by-ref contesta un cuerpo vacío de vez en cuando cuando las peticiones
    van muy seguidas, así que se reintenta con espera creciente antes de
    caer a la búsqueda.
    """
    for intento in range(1, REINTENTOS + 1):
        respuesta = sesion.get(
            API_PRODUCTO.format(ref=ref),
            params={"storeId": STORE_ID},
            timeout=25,
        )
        if respuesta.status_code == 200:
            datos = _json_o_bloqueo(respuesta)
            if datos.get("name"):
                return datos
        time.sleep(1.5 * intento)

    respuesta = sesion.get(
        API_BUSQUEDA, params={"q": ref, "storeId": STORE_ID}, timeout=25
    )
    if respuesta.status_code == 200:
        productos = _json_o_bloqueo(respuesta).get("products") or []
        for producto in productos:
            if str(producto.get("refId", "")) == ref:
                return producto
    return {}


def _formatear_precio(valor) -> str:
    """Normaliza el precio del API al formato histórico '0.00'."""
    try:
        return f"{float(valor):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def construir_fila(datos: dict, ref: str, url: str) -> dict:
    """Mapea el JSON del producto a las ocho columnas de salida."""
    precio = datos.get("price") or {}
    precio_actual = _formatear_precio(precio.get("listPrice"))
    precio_oferta = _formatear_precio(precio.get("basePrice"))

    # Mismo respaldo cruzado que traía la versión con Selenium: cuando la
    # tienda publica un solo precio, las dos columnas lo repiten.
    if precio_actual == "0.00":
        precio_actual = precio_oferta
    if precio_oferta == "0.00":
        precio_oferta = precio_actual

    imagenes = datos.get("images") or []
    url_imagen = imagenes[0].get("url", "") if imagenes else ""
    if not url_imagen:
        url_imagen = datos.get("imageUrl") or ""

    return {
        "SKU": str(datos.get("refId") or ref),
        "URL_PRODUCTO": url,
        "Producto": datos.get("name", ""),
        "Precio_Actual": precio_actual,
        "Precio_Oferta": precio_oferta,
        "URL_IMAGEN": url_imagen,
        "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Tienda": TIENDA,
    }


def main():
    if not os.path.exists(CSV_INPUT):
        print(f"❌ No existe: {CSV_INPUT}")
        return

    # dtype=str: si pandas infiere la columna SKU como numérica, el refId
    # llega con cola decimal ("897744.0") y el API no encuentra el producto.
    df_urls = pd.read_csv(CSV_INPUT, dtype=str)
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)

    procesados = cargar_procesados()
    print(f"📂 Historial: {len(procesados)} URLs ya procesadas.")

    sesion = requests.Session()
    sesion.headers.update(HEADERS)
    bloqueos_seguidos = 0

    with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if os.path.getsize(CSV_OUTPUT) == 0:
            writer.writeheader()

        barra = tqdm(
            list(df_urls.itertuples(index=False)),
            desc="heb",
            unit="url",
            initial=len(procesados),
        )
        for entrada in barra:
            url = str(entrada.URL_PRODUCTO)
            if url in procesados:
                continue

            ref = obtener_ref(getattr(entrada, "SKU", ""), url)
            if not ref:
                marcar_fallida(url, "sin refId en el CSV ni en la URL")
                procesados.add(url)
                continue

            try:
                datos = consultar_producto(sesion, ref)
            except BloqueoWAF as e:
                bloqueos_seguidos += 1
                tqdm.write(
                    f"   🛑 {ref}: {e} "
                    f"({bloqueos_seguidos}/{MAX_BLOQUEOS_SEGUIDOS})"
                )
                if bloqueos_seguidos >= MAX_BLOQUEOS_SEGUIDOS:
                    tqdm.write(
                        "🛑 Bloqueo sostenido del WAF: se corta la corrida "
                        "sin marcar fallidas. Reanuda más tarde."
                    )
                    break
                time.sleep(30)
                continue
            except requests.RequestException as e:
                tqdm.write(f"   ⚠️ {ref}: error de red. {str(e)[:80]}")
                marcar_fallida(url, str(e)[:200])
                procesados.add(url)
                continue

            bloqueos_seguidos = 0

            if not datos.get("name"):
                tqdm.write(f"   ⚠️ {ref}: sin datos extraídos.")
                marcar_fallida(url, "sin datos extraídos")
                procesados.add(url)
                continue

            fila = construir_fila(datos, ref, url)
            writer.writerow(fila)
            f.flush()
            procesados.add(url)
            tqdm.write(
                f"   ✅ {fila['SKU']} | {fila['Producto'][:30]} | "
                f"Actual: ${fila['Precio_Actual']} | "
                f"Oferta: ${fila['Precio_Oferta']}"
            )

            time.sleep(random.uniform(*PAUSA_ENTRE_PRODUCTOS))

    print(f"\n🎯 Proceso terminado. Archivo: {CSV_OUTPUT}")


if __name__ == "__main__":
    main()
