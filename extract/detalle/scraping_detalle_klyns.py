import os
import csv
import time
import re
import random
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as WW
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

# === Configuración ===
CSV_INPUT    = "./salida/urls/urls_klyns.csv"
CSV_OUTPUT   = "./salida/data/2026/09_septiembre/scraping_detalle_klyns.csv"
TIENDA       = "14"
# CSV aparte para URLs que fallaron, para no repetirlas al reanudar.
CSV_ESTADO_URLS = "./salida/data/2026/09_septiembre/scraping_detalle_klyns_fallidas.csv"


def marcar_fallida(url: str, detalle: str = "") -> None:
    """Registra una URL que no se pudo procesar en CSV_ESTADO_URLS."""
    es_nuevo = not os.path.exists(CSV_ESTADO_URLS) or os.stat(CSV_ESTADO_URLS).st_size == 0
    with open(CSV_ESTADO_URLS, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if es_nuevo:
            w.writerow(["URL_PRODUCTO", "Estatus", "Detalle", "Fecha_Hora_Captura"])
        w.writerow([url, "ERROR", detalle, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])


def cargar_procesados():
    """Une URLs exitosas (CSV_OUTPUT) y fallidas (CSV_ESTADO_URLS)."""
    procesados = set()
    if os.path.exists(CSV_OUTPUT) and os.path.getsize(CSV_OUTPUT) > 0:
        try:
            procesados |= set(pd.read_csv(CSV_OUTPUT)["URL_PRODUCTO"].tolist())
        except:
            pass
    if os.path.exists(CSV_ESTADO_URLS) and os.path.getsize(CSV_ESTADO_URLS) > 0:
        try:
            procesados |= set(pd.read_csv(CSV_ESTADO_URLS)["URL_PRODUCTO"].tolist())
        except:
            pass
    return procesados

def configurar_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-gpu")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

def clean_price(txt: str) -> str:
    if not txt: return "0.00"
    t = txt.replace(",", "").replace("$", "").strip()
    m = re.search(r"(\d+(?:\.\d{1,2})?)", t)
    return m.group(1) if m else "0.00"

def extraer_datos_klyns(driver, url):
    try:
        driver.get(url)
        wait = WW(driver, 15)
        
        # Esperar a que el nombre del producto cargue
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "vtex-store-components-3-x-productBrand")))
        time.sleep(2.5) 

        # 1. Nombre del Producto
        try:
            nombre = driver.find_element(By.CLASS_NAME, "vtex-store-components-3-x-productBrand").text.strip()
        except:
            nombre = "N/A"

        # 2. SKU (Referencia de VTEX)
        try:
            sku_el = driver.find_element(By.CLASS_NAME, "vtex-product-identifier-0-x-product-identifier__value")
            sku = sku_el.text.strip()
        except:
            sku = "N/A"

        # 3. Precios (Selectores estándar de Klyns)
        # Precio de Venta (Oferta/Selling)
        try:
            p_oferta_el = driver.find_element(By.CLASS_NAME, "vtex-product-price-1-x-sellingPriceValue")
            precio_oferta = clean_price(p_oferta_el.text)
        except:
            precio_oferta = "0.00"

        # Precio de Lista (Actual/Normal)
        try:
            p_actual_el = driver.find_element(By.CLASS_NAME, "vtex-product-price-1-x-listPriceValue")
            precio_actual = clean_price(p_actual_el.text)
        except:
            precio_actual = "0.00"

        # --- Lógica de Respaldo Solicitada ---
        if precio_oferta == "0.00":
            precio_oferta = precio_actual
        if precio_actual == "0.00":
            precio_actual = precio_oferta

        # 4. Imagen
        try:
            img_el = driver.find_element(By.CSS_SELECTOR, "img.vtex-store-components-3-x-productImageTag")
            url_imagen = img_el.get_attribute("src")
        except:
            url_imagen = ""

        return {
            "SKU": sku,
            "Producto": nombre,
            "Precio_Actual": precio_actual,
            "Precio_Oferta": precio_oferta,
            "URL_IMAGEN": url_imagen
        }
    except Exception as e:
        if "session" in str(e).lower():
            raise e # Lanza error para reiniciar el driver
        print(f"      ⚠️ Error en: {url[:50]}")
        return None

def main():
    if not os.path.exists(CSV_INPUT):
        print(f"❌ No existe: {CSV_INPUT}"); return

    df_urls = pd.read_csv(CSV_INPUT)
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
    
    driver = configurar_driver()
    barra = tqdm(total=len(df_urls), desc="klyns", unit="url", initial=len(cargar_procesados()))

    try:
        idx = 0
        while idx < len(df_urls):
            # Sistema de resume para continuar si falla
            procesados = cargar_procesados()

            row = df_urls.iloc[idx]
            url = row["URL_PRODUCTO"]

            if url in procesados:
                idx += 1
                barra.update(1)
                continue

            print(f"🔎 [{idx+1}/{len(df_urls)}] {url}")
            
            try:
                datos = extraer_datos_klyns(driver, url)
                if datos:
                    file_exists = os.path.exists(CSV_OUTPUT)
                    with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=["SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda"])
                        if not file_exists: writer.writeheader()
                        
                        writer.writerow({
                            "SKU": datos["SKU"],
                            "URL_PRODUCTO": url,
                            "Producto": datos["Producto"],
                            "Precio_Actual": datos["Precio_Actual"],
                            "Precio_Oferta": datos["Precio_Oferta"],
                            "URL_IMAGEN": datos["URL_IMAGEN"],
                            "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "Tienda": TIENDA
                        })
                    print(f"   ✅ Guardado: {datos['SKU']} | ${datos['Precio_Oferta']}")
                else:
                    marcar_fallida(url, "sin datos extraídos")

                idx += 1
                barra.update(1)
                time.sleep(random.uniform(1.0, 2.5))

            except Exception as e:
                print(f"   🔄 Error de navegador, reiniciando...")
                try: driver.quit()
                except: pass
                time.sleep(5)
                driver = configurar_driver()

    finally:
        try: driver.quit()
        except: pass
        barra.close()
        print(f"\n🎯 Scraping de Klyns finalizado.")

if __name__ == "__main__":
    main()