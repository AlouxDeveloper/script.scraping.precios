import os
import csv
import re
import time
import random
from datetime import datetime

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ===== Config =====
EXCEL_ENTRADA = "./salida/urls/urls_productos_similares.xlsx"
COLUMNA_URL   = "URL"
CSV_SALIDA    = "./salida/data/2026/08_agosto/scraping_detalle_similares.csv"
TIENDA        = "Farmacias Similares"

TIMEOUT = 15
ESPERA_INICIAL = (3.5, 5.0)
PAUSA_ENTRE_URLS = (1.0, 2.0)

# ===== Selectores VTEX (producto) =====
SEL_NOMBRE = ".vtex-store-components-3-x-productNameContainer"
SEL_SKU_VAL = ".vtex-product-identifier-0-x-product-identifier__value"
SEL_LIST_PRICE_CONTAINER = ".vtex-store-components-3-x-listPriceValue"
SEL_SELL_PRICE_CONTAINER = ".vtex-store-components-3-x-sellingPriceValue"
# Selector para la imagen principal del producto
SEL_IMAGEN = ".vtex-store-components-3-x-productImageTag--main, .vtex-store-components-3-x-productImageTag, .vtex-product-summary-2-x-imageTag"

# ===== Utilidades =====
def ensure_csv_header(path: str, headers: list):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        os.makedirs(os.path.dirname(path), exist_ok=True) # Crear carpeta si no existe
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)

def write_row_progress(path: str, row: dict):
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists or os.path.getsize(path) == 0:
            writer.writeheader()
        writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())

def first_text_or_empty(driver, css: str) -> str:
    try:
        el = driver.find_element(By.CSS_SELECTOR, css)
        return el.text.strip()
    except NoSuchElementException:
        return ""

def get_image_url(driver, css: str) -> str:
    """Extrae el atributo src de la imagen."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, css)
        return el.get_attribute("src")
    except NoSuchElementException:
        return ""

_money_re = re.compile(r"(\d[\d,]*)[.,](\d{2})")

def parse_price_from_container_text(txt: str) -> str:
    if not txt: return ""
    m = _money_re.search(txt.replace("\u00A0", " "))
    if not m: return ""
    entero = m.group(1).replace(",", "")
    frac = m.group(2)
    return f"{entero}.{frac}"

def get_price(driver, container_selector: str) -> str:
    try:
        el = driver.find_element(By.CSS_SELECTOR, container_selector)
        raw = el.text.strip()
        price = parse_price_from_container_text(raw)
        if price: return price
        
        integer_parts = el.find_elements(By.CSS_SELECTOR, ".vtex-product-summary-2-x-currencyInteger, .vtex-store-components-3-x-currencyInteger")
        fraction_parts = el.find_elements(By.CSS_SELECTOR, ".vtex-product-summary-2-x-currencyFraction, .vtex-store-components-3-x-currencyFraction")
        if integer_parts and fraction_parts:
            return f"{integer_parts[0].text.strip().replace(',', '')}.{fraction_parts[0].text.strip()}"
        return ""
    except NoSuchElementException:
        return ""

# ===== Main =====
def main():
    df = pd.read_excel(EXCEL_ENTRADA)
    if COLUMNA_URL not in df.columns:
        raise ValueError(f"El Excel debe tener la columna '{COLUMNA_URL}'.")
    urls = [str(u).strip() for u in df[COLUMNA_URL].dropna().tolist() if str(u).strip()]

    if not urls:
        print("⚠️ No hay URLs para procesar.")
        return

    # NUEVO ORDEN DE CABECERAS
    headers = ["SKU", "URL_Producto", "Producto", "Precio_Normal", "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda"]
    ensure_csv_header(CSV_SALIDA, headers)

    chrome_opts = Options()
    chrome_opts.add_argument("--start-maximized")
    chrome_opts.add_argument("--disable-blink-features=AutomationControlled")
    driver = webdriver.Chrome(options=chrome_opts)
    wait = WebDriverWait(driver, TIMEOUT)

    try:
        for i, url in enumerate(urls, 1):
            print(f"\n🔎 [{i}/{len(urls)}] Navegando: {url}")
            try:
                driver.get(url)
                time.sleep(random.uniform(*ESPERA_INICIAL))

                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, SEL_NOMBRE)))

                nombre = first_text_or_empty(driver, SEL_NOMBRE)
                sku = first_text_or_empty(driver, SEL_SKU_VAL)


                precio_normal = get_price(driver, SEL_LIST_PRICE_CONTAINER)
                if precio_normal == "":
                    precio_normal = get_price(driver, SEL_SELL_PRICE_CONTAINER)
                
                precio_oferta = get_price(driver, SEL_SELL_PRICE_CONTAINER)
                
                # EXTRAER IMAGEN
                url_imagen = get_image_url(driver, SEL_IMAGEN)
                
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # DICCIONARIO ACTUALIZADO
                row = {
                    "SKU": sku,
                    "URL_Producto": url,
                    "Producto": nombre,
                    "Precio_Normal": precio_normal,
                    "Precio_Oferta": precio_oferta,
                    "URL_IMAGEN": url_imagen,
                    "Fecha_Hora_Captura": ts,
                    "Tienda": TIENDA
                }

                write_row_progress(CSV_SALIDA, row)
                print(f"✅ Guardado: {nombre[:30]}... | Imagen detectada: {'Sí' if url_imagen else 'No'}")

            except Exception as e:
                print(f"💥 Error procesando URL: {e}")

            time.sleep(random.uniform(*PAUSA_ENTRE_URLS))

    finally:
        driver.quit()

    print(f"\n🎯 Listo. Revisa: {CSV_SALIDA}")

if __name__ == "__main__":
    main()