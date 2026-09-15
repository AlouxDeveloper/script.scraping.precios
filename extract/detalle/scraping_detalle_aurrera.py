from datetime import datetime
import csv
import os
import ssl
import time

import certifi
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Algunas PC (Windows con almacén de certificados incompleto) tiran
# "CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate" al
# bajar el chromedriver, porque el contexto SSL por defecto de Python usa
# el truststore del sistema en vez del bundle de certifi. Se fuerza aquí
# para toda la corrida, antes de que uc intente descargar nada.
ssl._create_default_https_context = lambda: ssl.create_default_context(
    cafile=certifi.where()
)

# === Configuración ===
INPUT_CSV = "./salida/urls/productos_aurrera.csv"
CSV_OUTPUT = "./salida/data/2026/09_septiembre/scraping_detalle_aurrera.csv"
TIENDA = "2"
# CSV aparte para URLs que fallaron, para no repetirlas al reanudar.
CSV_ESTADO_URLS = "./salida/data/2026/09_septiembre/scraping_detalle_aurrera_fallidas.csv"
# Version mayor del Chrome instalado (chrome://settings/help). uc descarga el
# chromedriver que declares aqui; si Chrome se autoactualiza sin avisar,
# ajusta este numero en vez de tocar el resto del script.
CHROME_VERSION_MAIN = 152

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

# Cargar progreso previo para reanudación automática
urls_procesadas = set()
if os.path.exists(CSV_OUTPUT) and os.stat(CSV_OUTPUT).st_size > 0:
    try:
        df_prev = pd.read_csv(CSV_OUTPUT)
        if "URL_PRODUCTO" in df_prev.columns:
            urls_procesadas = set(df_prev["URL_PRODUCTO"].dropna().astype(str).tolist())
    except:
        pass

if os.path.exists(CSV_ESTADO_URLS) and os.stat(CSV_ESTADO_URLS).st_size > 0:
    try:
        df_fallidas = pd.read_csv(CSV_ESTADO_URLS)
        if "URL_PRODUCTO" in df_fallidas.columns:
            urls_procesadas |= set(df_fallidas["URL_PRODUCTO"].dropna().astype(str).tolist())
    except Exception as e:
        print(f"⚠️ Alerta leyendo URLs fallidas previas: {e}")

# Manejo de Encoding para lectura segura
try:
    try:
        df_urls = pd.read_csv(INPUT_CSV, encoding='utf-8')
    except UnicodeDecodeError:
        df_urls = pd.read_csv(INPUT_CSV, encoding='latin-1')
    lista_productos = df_urls.to_dict('records')
except Exception as e:
    print(f"❌ Error al leer el archivo de URLs: {e}")
    exit()

print(f"📂 Avance detectado: {len(urls_procesadas)} ya procesadas.")
print(f"🚀 Iniciando captura blindada (Abriendo y cerrando navegador por producto)...")

# === Bucle de Scraping ===
for i, item in enumerate(lista_productos, 1):
    url = item['URL']

    if url in urls_procesadas:
        continue

    print(f"\n🔍 [{i}/{len(lista_productos)}] Procesando: {url}")

    driver = None
    try:
        # Configuración de Navegador en cada ciclo (Se crea desde cero)
        options = uc.ChromeOptions()
        options.add_argument("--window-size=1280,1000")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # version_main fija: el autodetect de uc bajo un chromedriver de una
        # version mayor a la instalada (153 vs Chrome 152 real) y tumbaba
        # cada sesion con "session not created". Se fija a mano y se ajusta
        # aqui cuando Chrome se actualice.
        driver = uc.Chrome(
            options=options, use_subprocess=True,
            version_main=CHROME_VERSION_MAIN,
        )
        wait = WebDriverWait(driver, 15)

        driver.get(url)

        # Esperar a que cargue el título (ID único del producto principal)
        wait.until(EC.presence_of_element_located((By.ID, "main-title")))

        # Scroll preventivo para cargar componentes dinámicos
        driver.execute_script("window.scrollBy(0, 350);")
        time.sleep(1.5)
        
        # Esperar que aparezca el contenedor del precio antes de extraerlo
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="add-to-cart-price-atf"]')))
        
        # 1. Extraer SKU desde la URL
        sku = url.split('/')[-1].split('?')[0]

        # 2. Título (Usando el ID que enviaste)
        try:
            titulo = driver.find_element(By.ID, "main-title").text.strip()
        except:
            titulo = item.get('Nombre', 'Sin nombre')

        # 3. LÓGICA DE PRECIOS BLINDADA
        precio_normal = "0"
        precio_oferta = "0"
        
        try:
            contenedor_precio_principal = driver.find_element(By.CSS_SELECTOR, '[data-testid="add-to-cart-price-atf"]')
            precio_hero_elem = contenedor_precio_principal.find_element(By.CSS_SELECTOR, '[data-seo-id="hero-price"]')
            precio_detectado = precio_hero_elem.text.replace('$', '').replace(',', '').strip()
            
            try:
                precio_tachado_elem = contenedor_precio_principal.find_element(By.CSS_SELECTOR, 'span.strike')
                precio_normal = precio_tachado_elem.text.replace('$', '').replace(',', '').strip()
                precio_oferta = precio_detectado
            except NoSuchElementException:
                precio_normal = precio_detectado
                precio_oferta = precio_detectado

        except Exception as e:
            try:
                precio_detectado = driver.find_element(By.CSS_SELECTOR, '[data-seo-id="hero-price"]').text.replace('$', '').replace(',', '').strip()
                precio_normal = precio_detectado
                precio_oferta = precio_detectado
            except:
                precio_normal = "No disponible"
                precio_oferta = "No disponible"

        # 4. IMAGEN BLINDADA
        try:
            contenedor_img = driver.find_element(By.CSS_SELECTOR, 'div[data-seo-id="hero-carousel-image"]')
            imagen_url = contenedor_img.find_element(By.TAG_NAME, "img").get_attribute("src")
        except:
            imagen_url = "No disponible"

        # 5. Guardado en tiempo real
        fila = {
            "SKU": sku,
            "URL_PRODUCTO": url,
            "Producto": titulo,
            "Precio_Actual": precio_normal,
            "Precio_Oferta": precio_oferta,
            "URL_IMAGEN": imagen_url,
            "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Tienda": TIENDA
        }

        with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ENCABEZADOS)
            writer.writerow(fila)

        urls_procesadas.add(url)
        print(f"   ✅ Guardado: {titulo[:35]}... | Actual: ${precio_normal} | Oferta: ${precio_oferta}")

    except Exception as e:
        print(f"   ❌ Error en registro {i}: Verifique si hay un bloqueo o Captcha.")
        es_nuevo = not os.path.exists(CSV_ESTADO_URLS) or os.stat(CSV_ESTADO_URLS).st_size == 0
        with open(CSV_ESTADO_URLS, "a", newline="", encoding="utf-8") as f_estado:
            writer_estado = csv.writer(f_estado)
            if es_nuevo:
                writer_estado.writerow(["URL_PRODUCTO", "Estatus", "Detalle", "Fecha_Hora_Captura"])
            writer_estado.writerow([url, "ERROR", str(e)[:200], datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        urls_procesadas.add(url)
        time.sleep(2)
        
    finally:
        # Se destruye por completo la ventana de Chrome al terminar la URL actual
        if driver:
            driver.quit()
        # Descanso entre ventanas para enfriar peticiones
        time.sleep(2)

print(f"\n📦 Proceso masivo finalizado. Resultados en: {CSV_OUTPUT}")