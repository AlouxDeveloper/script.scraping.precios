import os
import csv
import time
import re
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ========== Configuración ==========
CSV_INPUT  = "./salida/urls/urls_soriana.csv"
CSV_OUTPUT = "./salida/data/2026/08_agosto/scraping_detalle_soriana.csv"
TIENDA     = "Soriana"

FIELDNAMES = [
    "SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", 
    "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda"
]

# ========== Helpers de Limpieza ==========
def clean_num(txt: str):
    if txt is None: return "0.00"
    # Elimina $, comas, espacios y textos como "M.N."
    t = str(txt).replace("$", "").replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d{1,2})?)", t)
    return m.group(1) if m else "0.00"

def leer_precios_soriana(driver):
    v_normal = None
    v_oferta = None

    # 1) Intentar con inputs ocultos (CleverTap) - Son los más exactos
    try:
        v_oferta = clean_num(driver.find_element(By.ID, "clevertap-price").get_attribute("value"))
    except: pass
    try:
        v_normal = clean_num(driver.find_element(By.ID, "clevertap-list-price").get_attribute("value"))
    except: pass

    # 2) Fallback a texto visible
    if v_oferta == "0.00":
        try:
            txt = driver.find_element(By.CSS_SELECTOR, ".cart-price .value, .price .value").text
            v_oferta = clean_num(txt)
        except: pass
    
    if v_normal == "0.00" or v_normal is None:
        try:
            txt = driver.find_element(By.CSS_SELECTOR, ".strike-through .value, .price-standard").text
            v_normal = clean_num(txt)
        except: pass

    # 3) Lógica de consistencia
    if not v_normal or v_normal == "0.00": v_normal = v_oferta
    if not v_oferta or v_oferta == "0.00": v_oferta = v_normal
    
    return v_normal, v_oferta

def configurar_driver():
    opts = Options()
    opts.add_argument("--headless=new") 
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

# ========== Main ==========
def main():
    if not os.path.exists(CSV_INPUT):
        print(f"❌ No existe el archivo de URLs: {CSV_INPUT}"); return

    df_urls = pd.read_csv(CSV_INPUT)
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
    
    # Cargar progreso para saltar URLs ya hechas
    urls_procesadas = set()
    if os.path.exists(CSV_OUTPUT):
        try:
            df_existente = pd.read_csv(CSV_OUTPUT)
            urls_procesadas = set(df_existente["URL_PRODUCTO"].astype(str).tolist())
        except: pass

    driver = configurar_driver()
    
    try:
        with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if not urls_procesadas:
                writer.writeheader()

            for i, row in df_urls.iterrows():
                url = str(row["URL_PRODUCTO"])
                if url in urls_procesadas: continue

                print(f"🔎 [{i+1}/{len(df_urls)}] Procesando: {url}")
                
                try:
                    driver.get(url)
                    wait = WebDriverWait(driver, 15)
                    
                    # Esperar carga del contenedor de producto
                    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "product-detail")))
                    
                    # 1. SKU: Extraer del final de la URL (ej: 390288.html)
                    sku_match = re.search(r'/(\d+)\.html', url)
                    sku = sku_match.group(1) if sku_match else "N/A"

                    # 2. Nombre
                    try:
                        producto = driver.find_element(By.CLASS_NAME, "product-name").text.strip()
                    except:
                        producto = row["Producto"]

                    # 3. Precios
                    precio_actual, precio_oferta = leer_precios_soriana(driver)

                    # 4. URL IMAGEN (Basado en la etiqueta que me pasaste)
                    try:
                        img_elem = driver.find_element(By.CSS_SELECTOR, "img.swiper-lazy-loaded, img.primary-image")
                        url_img = img_elem.get_attribute("src")
                    except:
                        # Si no ha cargado el swiper, intentar construirla con el SKU
                        url_img = f"https://www.soriana.com/dw/image/v2/BGBD_PRD/on/demandware.static/-/Sites-soriana-grocery-master-catalog/default/images/product/{sku}_A.jpg"

                    writer.writerow({
                        "SKU": sku,
                        "URL_PRODUCTO": url,
                        "Producto": producto,
                        "Precio_Actual": precio_actual,
                        "Precio_Oferta": precio_oferta,
                        "URL_IMAGEN": url_img,
                        "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Tienda": TIENDA
                    })
                    f.flush()
                    urls_procesadas.add(url)
                    print(f"   ✅ {sku} | ${precio_oferta}")

                except Exception as e:
                    print(f"   ⚠️ Falló la extracción en esta URL.")
                
                time.sleep(1.2) # Evitar bloqueos

    finally:
        driver.quit()
        print(f"\n🎯 Proceso terminado. Archivo: {CSV_OUTPUT}")

if __name__ == "__main__":
    main()