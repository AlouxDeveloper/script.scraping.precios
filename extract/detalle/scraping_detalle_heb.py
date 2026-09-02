import os
import csv
import time
import random
import re
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as WW
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# === Configuración ===
CSV_INPUT    = "./salida/urls/urls_scraping_heb.csv"
CSV_OUTPUT   = "./salida/data/2026/08_agosto/scraping_detalle_heb.csv"
TIENDA       = "HEB"

def configurar_driver():
    print("🌐 Iniciando nueva sesión del navegador...")
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    # En Mac, a veces ayuda desactivar la aceleración de hardware para evitar crashes
    opts.add_argument("--disable-gpu") 
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(30) # Evita que se quede colgado infinitamente
    return driver

def clean_price(txt: str) -> str:
    if not txt: return "0.00"
    t = txt.replace(",", "").replace("$", "").strip()
    m = re.search(r"(\d+(?:\.\d{1,2})?)", t)
    return m.group(1) if m else "0.00"

def extraer_datos_pdp(driver, url):
    try:
        driver.get(url)
        wait = WW(driver, 20)
        
        # Esperar a que el nombre sea visible
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "vtex-store-components-3-x-productBrand")))
        time.sleep(2) 
        
        # 1. Nombre e Identificadores
        nombre = driver.find_element(By.CLASS_NAME, "vtex-store-components-3-x-productBrand").text.strip()
        sku_raw = driver.find_element(By.CLASS_NAME, "vtex-product-identifier-0-x-product-identifier__value").text.strip()
        sku_limpio = sku_raw.replace("MXYZ_", "").strip()

        # 2. Precios
        try:
            p_actual_raw = driver.find_element(By.CLASS_NAME, "vtex-product-price-1-x-listPriceValue").text
            precio_actual = clean_price(p_actual_raw)
        except:
            precio_actual = "0.00"

        try:
            p_oferta_raw = driver.find_element(By.CLASS_NAME, "price").text
            precio_oferta = clean_price(p_oferta_raw)
        except:
            precio_oferta = "0.00"

        # --- Lógica de Respaldo de Precios ---
        if precio_actual == "0.00": precio_actual = precio_oferta
        if precio_oferta == "0.00": precio_oferta = precio_actual

        # 3. Imagen
        try:
            img_el = driver.find_element(By.CSS_SELECTOR, ".vtex-store-components-3-x-productImageTag, img[itemprop='image']")
            url_imagen = img_el.get_attribute("src")
        except:
            url_imagen = ""

        return {
            "SKU": sku_limpio,
            "Producto": nombre,
            "Precio_Actual": precio_actual,
            "Precio_Oferta": precio_oferta,
            "URL_IMAGEN": url_imagen
        }
    except Exception as e:
        # Si el error es de conexión o el navegador se cerró, lanzamos la excepción para reiniciar
        if "session" in str(e).lower() or "unreachable" in str(e).lower():
            raise e 
        print(f"      ⚠️ No se pudo extraer datos (posible producto agotado o error de carga)")
        return None

def main():
    if not os.path.exists(CSV_INPUT):
        print(f"❌ No existe: {CSV_INPUT}"); return

    df_urls = pd.read_csv(CSV_INPUT)
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
    
    driver = configurar_driver()
    
    try:
        idx = 0
        while idx < len(df_urls):
            # Recargar lista de procesados en cada iteración por seguridad
            procesados = set()
            if os.path.exists(CSV_OUTPUT):
                try:
                    df_ex = pd.read_csv(CSV_OUTPUT)
                    procesados = set(df_ex["URL_PRODUCTO"].tolist())
                except: pass

            row = df_urls.iloc[idx]
            url = row["URL_PRODUCTO"]

            if url in procesados:
                idx += 1
                continue

            print(f"🔎 [{idx+1}/{len(df_urls)}] {url}")
            
            try:
                datos = extraer_datos_pdp(driver, url)
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
                    print(f"   ✅ Guardado: ${datos['Precio_Oferta']}")
                
                idx += 1 # Solo avanzamos si no hubo error de sesión
                time.sleep(random.uniform(1.5, 3.0))

            except Exception as e:
                print(f"   💥 Error de sesión detectado: {str(e)[:50]}")
                print("   🔄 Reiniciando navegador y reintentando producto actual...")
                try: driver.quit()
                except: pass
                time.sleep(5)
                driver = configurar_driver()
                # No incrementamos idx para que reintente el mismo producto

    finally:
        try: driver.quit()
        except: pass
        print(f"\n🎯 Proceso finalizado.")

if __name__ == "__main__":
    main()