import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tqdm import tqdm
from datetime import datetime
import time
import csv
import os

from monitoreo import MonitorFallos, configurar_logger, es_pagina_bloqueada

# === Configuración ===
EXCEL_PATH = "./data/data_scraping_guadalajara.xlsx"
CSV_OUTPUT = "./salida/data/2026/09_septiembre/scraping_detalle_guadalajara.csv"

os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)

# === Leer Excel ===
df = pd.read_excel(EXCEL_PATH)
urls_busqueda = df["URL_Producto"].astype(str).tolist()

# === CONTROL DE AVANCE INCREMENTAL ===
urls_procesadas = set()
if os.path.exists(CSV_OUTPUT) and os.stat(CSV_OUTPUT).st_size > 0:
    try:
        df_prev = pd.read_csv(CSV_OUTPUT)
        if "URL_Producto" in df_prev.columns:
            urls_procesadas = set(
                df_prev["URL_Producto"].dropna().astype(str).tolist()
            )
    except Exception as e:
        print(f"⚠️ Alerta leyendo avance previo: {e}")

print(f"📂 Historial: {len(urls_procesadas)} URLs ya se encuentran en el archivo de salida.")

logger = configurar_logger("guadalajara")
monitor = MonitorFallos(tienda="guadalajara", logger=logger)

# === Bucle de Scraping (Se mantiene idéntico) ===
barra = tqdm(urls_busqueda, desc="guadalajara", unit="url")
for i, url in enumerate(barra, start=1):
    if not url.startswith("http"):
        tqdm.write(f"⚠️ [{i}/{len(urls_busqueda)}] URL no válida: {url}")
        continue

    if url in urls_procesadas:
        continue

    barra.set_postfix(exitosas=monitor.exitos)
    tqdm.write(f"🔎 [{i}/{len(urls_busqueda)}] Procesando: {url}")

    driver = None
    try:
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--log-level=3")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 15)

        driver.get(url)

        if es_pagina_bloqueada(driver.page_source):
            monitor.registrar_fallo("bloqueo_detectado")
            continue

        try:
            # 1. Esperar al nombre del producto
            try:
                nombre_element = wait.until(EC.presence_of_element_located((By.ID, "fgProductName")))
            except:
                nombre_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1")))
                
            nombre = nombre_element.get_attribute("innerText").strip()
            
            # 2. Extraer SKU (ID)
            sku_limpio = "N/A"
            try:
                sku_element = driver.find_element(By.CSS_SELECTOR, "span.sku.product-key-pdp.skuprdt")
                sku_limpio = "".join(filter(str.isdigit, sku_element.get_attribute("innerText")))
            except:
                pass
                
            if not sku_limpio or sku_limpio == "N/A":
                sku_limpio = "".join(filter(str.isdigit, url.split('-')[-1]))

            # 3. Extraer Imagen (Corregido con la clase real que mandaste)
            try:
                img_element = driver.find_element(By.CSS_SELECTOR, "img.xzoom, img.img-fluid.xzoom")
                url_imagen = img_element.get_attribute("src")
            except:
                url_imagen = "N/A"

            # 4. Lógica de Precios Exacta para el HTML Mandado
            precio_normal = "N/A"
            precio_actual = "N/A"

            try:
                # Caso A: Con descuento (Buscamos los atributos 'content' directo del HTML provisto)
                val_normal_elem = driver.find_element(By.CSS_SELECTOR, ".price-before .value")
                precio_normal = val_normal_elem.get_attribute("content").strip()
                
                val_oferta_elem = driver.find_element(By.CSS_SELECTOR, ".sales.offer-mini-cart .value")
                precio_actual = val_oferta_elem.get_attribute("content").strip()
            except:
                # Caso B: Respaldo si no encuentra atributos o es precio regular (sin descuento)
                try:
                    precio_elem = driver.find_element(By.CSS_SELECTOR, ".sales .value, .price .value")
                    precio_actual = precio_elem.get_attribute("content").strip()
                    precio_normal = precio_actual
                except:
                    try:
                        # Respaldo de texto crudo si falla el atributo content
                        raw_text = driver.find_element(By.CSS_SELECTOR, ".sales, .price").get_attribute("innerText")
                        precio_actual = "".join(c for c in raw_text if c.isdigit() or c == '.')
                        precio_normal = precio_actual
                    except:
                        pass

            resultado = {
                "SKU": sku_limpio,
                "URL_Producto": url,
                "Producto": nombre,
                "Precio_Normal": precio_normal,
                "Precio_Oferta": precio_actual,
                "URL_IMAGEN": url_imagen,
                "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Tienda": "1",
            }

            # Guardar en CSV inmediatamente (append mode)
            file_exists = os.path.isfile(CSV_OUTPUT)
            with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as output_file:
                writer = csv.DictWriter(output_file, fieldnames=resultado.keys())
                if not file_exists or os.stat(CSV_OUTPUT).st_size == 0:
                    writer.writeheader()
                writer.writerow(resultado)

            urls_procesadas.add(url)
            monitor.registrar_exito()
            tqdm.write(
                f"✅ Éxito: {sku_limpio} | {nombre[:25]} | "
                f"Normal: {precio_normal} | Oferta: {precio_actual}"
            )

        except Exception as e:
            monitor.registrar_fallo(str(e))
            tqdm.write(f"⚠️ Error al extraer datos de la página: {url} | Detalle: {e}")

    except Exception as e:
        monitor.registrar_fallo(str(e))
        tqdm.write(f"❌ Error de conexión/driver: {e}")
    
    finally:
        if driver:
            driver.quit()
        time.sleep(1)

print("\n✅ Proceso terminado.")