import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tqdm import tqdm
from datetime import datetime
import time
import csv
import os

# === Configuración ===
INPUT_CSV = "./salida/urls/productos_walmart.csv"
CSV_OUTPUT = "./salida/data/2026/09_septiembre/scraping_detalle_walmart.csv"
TIENDA = "12"

# Versión mayor del Chrome instalado en la máquina donde corre el script.
# undetected_chromedriver 3.5.5 no la detecta bien: baja el chromedriver de
# la última versión publicada (153) y revienta contra un Chrome 152 con
# "This version of ChromeDriver only supports Chrome version 153".
# Al actualizarse Chrome hay que subir este número.
VERSION_CHROME = 152

ENCABEZADOS = [
    "SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", 
    "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda"
]

# Asegurar carpetas y archivo de salida
os.makedirs(os.path.dirname(CSV_OUTPUT) or ".", exist_ok=True)
if not os.path.exists(CSV_OUTPUT):
    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ENCABEZADOS)
        writer.writeheader()

# === CONTROL DE AVANCE INCREMENTAL ===
urls_procesadas = set()
if os.path.exists(CSV_OUTPUT) and os.stat(CSV_OUTPUT).st_size > 0:
    try:
        df_prev = pd.read_csv(CSV_OUTPUT)
        if "URL_PRODUCTO" in df_prev.columns:
            urls_procesadas = set(df_prev["URL_PRODUCTO"].dropna().astype(str).tolist())
    except Exception as e:
        print(f"⚠️ Alerta leyendo avance previo: {e}")

# Manejo de Encoding
try:
    try:
        df_urls = pd.read_csv(INPUT_CSV, encoding='utf-8')
    except UnicodeDecodeError:
        df_urls = pd.read_csv(INPUT_CSV, encoding='latin-1')
    lista_productos = df_urls.to_dict('records')
except Exception as e:
    print(f"❌ Error al leer el archivo de URLs: {e}")
    exit()

print(f"📂 Historial: {len(urls_procesadas)} URLs ya se encuentran en el archivo de salida.")
print(f"🚀 Iniciando captura blindada (Abriendo y cerrando navegador por producto)...")

# === Bucle de Scraping ===
barra = tqdm(lista_productos, desc="walmart", unit="url")
for i, item in enumerate(barra, 1):
    url = item['URL']

    if url in urls_procesadas:
        continue

    tqdm.write(f"\n🔍 [{i}/{len(lista_productos)}] Procesando: {url}")

    driver = None
    try:
        options = uc.ChromeOptions()
        options.add_argument("--window-size=1280,1000")
        options.add_argument("--disable-blink-features=AutomationControlled")

        driver = uc.Chrome(
            options=options,
            use_subprocess=True,
            version_main=VERSION_CHROME,
        )
        wait = WebDriverWait(driver, 25)

        # Cargar la URL
        driver.get(url)

        # Pausa dura de control para dar estabilidad a la carga
        time.sleep(4)

        # Esperar a que cargue el título principal
        wait.until(EC.presence_of_element_located((By.ID, "main-title")))

        # Scroll sutil para activar lazy loading
        driver.execute_script("window.scrollBy(0, 350);")
        time.sleep(2)

        sku = url.split('/')[-1].split('?')[0]

        try:
            titulo = driver.find_element(By.ID, "main-title").text.strip()
        except:
            titulo = item.get('Nombre', 'Sin nombre')
        tqdm.write(f"   🔬 Título capturado: {titulo[:60]}")

        # === LÓGICA DE PRECIOS BLINDADA PARA WALMART ===
        precio_actual = "0"
        precio_oferta = "0"

        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-seo-id="hero-price"]')))

            precio_hero_elem = driver.find_element(By.CSS_SELECTOR, '[data-seo-id="hero-price"]')
            precio_detectado = precio_hero_elem.text.replace('$', '').replace(',', '').strip()

            try:
                precio_tachado_elem = driver.find_element(By.CSS_SELECTOR, '[data-seo-id="strike-through-price"]')
                precio_actual = precio_tachado_elem.text.replace('$', '').replace(',', '').strip()
                precio_oferta = precio_detectado
            except NoSuchElementException:
                precio_actual = precio_detectado
                precio_oferta = precio_detectado

        except Exception:
            precio_actual = "No disponible"
            precio_oferta = "No disponible"
        tqdm.write(f"   🔬 Precio capturado: actual={precio_actual} oferta={precio_oferta}")

        # 4. IMAGEN BLINDADA
        try:
            contenedor_img = driver.find_element(By.CSS_SELECTOR, 'div[data-seo-id="hero-carousel-image"]')
            imagen_url = contenedor_img.find_element(By.TAG_NAME, "img").get_attribute("src")
        except:
            imagen_url = "No disponible"
        tqdm.write(f"   🔬 Imagen capturada: {imagen_url}")

        # 5. Guardado
        fila = {
            "SKU": sku,
            "URL_PRODUCTO": url,
            "Producto": titulo,
            "Precio_Actual": precio_actual,
            "Precio_Oferta": precio_oferta,
            "URL_IMAGEN": imagen_url,
            "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Tienda": TIENDA
        }

        with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ENCABEZADOS)
            writer.writerow(fila)

        urls_procesadas.add(url)
        tqdm.write(
            f"   ✅ Guardado: {titulo[:30]}... | "
            f"Actual: ${precio_actual} | Oferta: ${precio_oferta}"
        )

    except Exception as e:
        tqdm.write(f"   ❌ Saltó la ventana {i} por error o bloqueo. Detalle: {e}")
        time.sleep(3)
        
    finally:
        if driver:
            driver.quit()
        time.sleep(2)

print(f"\n📦 Proceso masivo finalizado. Resultados en: {CSV_OUTPUT}")