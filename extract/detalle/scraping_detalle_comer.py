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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ========== Configuración ==========
CSV_INPUT  = "./salida/urls/urls_lacomer.csv"
CSV_OUTPUT = "./salida/data/2026/08_agosto/scraping_detalle_comer.csv"
TIENDA     = "La Comer"

FIELDNAMES = [
    "SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", 
    "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda"
]

def configurar_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Selenium 4 gestiona el driver nativamente sin requerir ChromeDriverManager
    driver = webdriver.Chrome(options=opts)
    
    # Ocultar rastro de automatización en navigator
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def extraer_sku_de_url(url):
    match = re.search(r'detarticulo/(\d+)', url)
    return match.group(1) if match else "N/A"

def establecer_sucursal(driver):
    print("🌐 Validando sesión y sucursal...")
    driver.get("https://www.lacomer.com.mx/lacomer/#!/home")
    time.sleep(12) 

def main():
    if not os.path.exists(CSV_INPUT):
        print(f"❌ No existe: {CSV_INPUT}")
        return

    df_urls = pd.read_csv(CSV_INPUT)
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
    
    urls_procesadas = set()
    if os.path.exists(CSV_OUTPUT):
        try:
            df_existente = pd.read_csv(CSV_OUTPUT)
            urls_procesadas = set(df_existente["URL_PRODUCTO"].astype(str).tolist())
        except:
            pass

    driver = configurar_driver()
    establecer_sucursal(driver)
    
    count = 0
    try:
        with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if not urls_procesadas and (not os.path.exists(CSV_OUTPUT) or os.stat(CSV_OUTPUT).st_size == 0):
                writer.writeheader()

            for i, row in df_urls.iterrows():
                url = str(row["URL_PRODUCTO"])
                if url in urls_procesadas:
                    continue

                sku = extraer_sku_de_url(url)
                print(f"🔎 [{i+1}/{len(df_urls)}] Procesando SKU: {sku}")
                
                # Reiniciar driver cada 50 items para liberar memoria
                if count > 0 and count % 50 == 0:
                    driver.quit()
                    time.sleep(3)
                    driver = configurar_driver()
                    establecer_sucursal(driver)

                try:
                    driver.get(url)
                    wait = WebDriverWait(driver, 15)
                    
                    # Esperar a que el nombre cargue
                    nombre_elem = wait.until(EC.visibility_of_element_located((
                        By.CSS_SELECTOR, ".txt-product-name, .det_art_nombre"
                    )))
                    nombre = nombre_elem.text.replace("\n", " ").strip()
                    
                    # Precio
                    try:
                        precio_raw = driver.find_element(By.CLASS_NAME, "txt-whitout-line").text
                        precio_limpio = "".join(filter(lambda x: x.isdigit() or x == '.', precio_raw))
                    except:
                        precio_limpio = "0.00"

                    # Imagen
                    try:
                        url_img = driver.find_element(By.ID, "target-src").get_attribute("src")
                    except:
                        url_img = f"https://www.lacomer.com.mx/superc/img_art/{sku}_1.jpg"

                    writer.writerow({
                        "SKU": sku, 
                        "URL_PRODUCTO": url, 
                        "Producto": nombre,
                        "Precio_Actual": precio_limpio, 
                        "Precio_Oferta": precio_limpio,
                        "URL_IMAGEN": url_img, 
                        "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Tienda": TIENDA
                    })
                    f.flush()
                    urls_procesadas.add(url)
                    count += 1
                    print(f"   ✅ Guardado: {precio_limpio}")

                except Exception:
                    print(f"   ⚠️ Error en SKU {sku}. Posible producto no disponible.")
                
                time.sleep(random.uniform(1.5, 3.0))

    except Exception as e:
        print(f"❌ Error crítico: {e}")
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()