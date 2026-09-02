import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import time
import csv
import os
import random

# === Configuración ===
CSV_INPUT = "./salida/urls/urls_productos_farmalisto.csv" 
CSV_OUTPUT = "./salida/data/2026/08_agosto/scraping_detalle_farmalisto.csv"
COLUMNA_URL = "URL" 
TIENDA = "Farmalisto"
CSV_HEADERS = ["SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda"]

def limpiar_precio(texto_precio):
    if not texto_precio:
        return "No disponible"
    try:
        return texto_precio.replace('$', '').replace(',', '').strip()
    except:
        return "No disponible"

def main():
    if not os.path.exists(CSV_INPUT):
        print(f"❌ No se encontró el archivo de entrada en {CSV_INPUT}")
        return
    
    # 1. Cargar progreso previo para no repetir URLs si se corta
    urls_procesadas = set()
    if os.path.exists(CSV_OUTPUT) and os.stat(CSV_OUTPUT).st_size > 0:
        try:
            urls_procesadas = set(pd.read_csv(CSV_OUTPUT)[COLUMNA_URL].astype(str).tolist())
        except: 
            pass

    df_input = pd.read_csv(CSV_INPUT)
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)

    print(f"📂 Avance: {len(urls_procesadas)} de {len(df_input)} URLs ya procesadas.")
    print("🚀 Levantando instancia única de Selenium Chrome...")

    # 2. Configurar y levantar el navegador una sola vez
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--log-level=3")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    
    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 10)

    try:
        with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            if os.path.getsize(CSV_OUTPUT) == 0 if os.path.exists(CSV_OUTPUT) else True:
                w.writeheader()
            
            for i, row in df_input.iterrows():
                url = str(row[COLUMNA_URL]).strip()
                if url in urls_procesadas or url == "nan": 
                    continue

                print(f"🔎 [{i+1}/{len(df_input)}] Navegando a: {url}")
                
                try:
                    # Navegación directa en la misma ventana abierta
                    driver.get(url)
                    
                    # Espera sutil a que cargue la estructura del título para asegurar el renderizado
                    try:
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.product_title, h1")))
                    except:
                        print("    ⚠️ Tiempo de espera agotado para el título. Saltando...")
                        continue

                    # Un pequeño scroll para activar el lazyload de las imágenes e inyectar naturalidad
                    driver.execute_script("window.scrollBy(0, 250);")
                    time.sleep(0.5)

                    # 1. Extraer Nombre del Producto
                    try:
                        nombre_elem = driver.find_element(By.CSS_SELECTOR, "h1.product_title")
                        producto = nombre_elem.get_attribute("innerText").strip()
                    except:
                        producto = "No disponible"

                    # 2. Extraer SKU (div.product-reference span)
                    try:
                        sku_elem = driver.find_element(By.CSS_SELECTOR, ".product-reference span")
                        sku = sku_elem.get_attribute("innerText").strip()
                    except:
                        sku = "N/A"

                    # 3. CORRECCIÓN DE IMAGEN: Captura doble segura de src y data-src
                    try:
                        img_elem = driver.find_element(By.CSS_SELECTOR, "img.img-fluid")
                        url_imagen = img_elem.get_attribute("src") or img_elem.get_attribute("data-src") or "No disponible"
                    except:
                        url_imagen = "No disponible"

                    # 4. Lógica de Precios Estricta
                    precio_normal = "No disponible"
                    precio_oferta = "No disponible"

                    # A) Intentar capturar precio normal con descuento
                    try:
                        reg_price_elem = driver.find_element(By.CSS_SELECTOR, ".product-discount .regular-price")
                        precio_normal = limpiar_precio(reg_price_elem.get_attribute("innerText"))
                    except:
                        pass

                    # B) Intentar capturar precio de oferta (current-price-display)
                    try:
                        curr_price_elem = driver.find_element(By.CSS_SELECTOR, ".current-price-display")
                        precio_oferta = curr_price_elem.get_attribute("content")
                        if not precio_oferta: # Respaldo si no viene el atributo content
                            precio_oferta = limpiar_precio(curr_price_elem.get_attribute("innerText"))
                    except:
                        pass

                    # Ajustes cruzados si faltan contenedores de descuento
                    if precio_normal == "No disponible" and precio_oferta != "No disponible":
                        precio_normal = precio_oferta
                    elif precio_oferta == "No disponible" and precio_normal != "No disponible":
                        precio_oferta = precio_normal

                    # Garantizar por regla de negocio que la oferta nunca supera al regular
                    if precio_normal != "No disponible" and precio_oferta != "No disponible":
                        try:
                            if float(precio_oferta) > float(precio_normal):
                                precio_oferta = precio_normal
                        except:
                            pass

                    # Escribir fila limpia en el CSV
                    w.writerow({
                        "SKU": sku, 
                        "URL_PRODUCTO": url, 
                        "Producto": producto,
                        "Precio_Actual": precio_normal, 
                        "Precio_Oferta": precio_oferta,
                        "URL_IMAGEN": url_imagen,
                        "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "Tienda": TIENDA,
                    })
                    f.flush()
                    urls_procesadas.add(url)
                    print(f"    ✅ Completado: SKU {sku} | Reg: ${precio_normal} | Of: ${precio_oferta}")
                    
                    # Delay moderado para no activar alertas de peticiones en ráfaga
                    time.sleep(random.uniform(2, 4))

                except Exception as e:
                    print(f"    ❌ Error procesando el producto actual: {e}")
                    time.sleep(2)

    finally:
        # Cerrar el navegador únicamente cuando termine el ciclo completo o detengas la ejecución
        if driver:
            driver.quit()
        print("\n✅ Proceso de Selenium finalizado de forma controlada.")

if __name__ == "__main__":
    main()