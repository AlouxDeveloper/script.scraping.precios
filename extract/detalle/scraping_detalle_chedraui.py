import pandas as pd
import requests
import csv
import time
import re
import os
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# === Configuración ===
CSV_INPUT = "./salida/urls/urls_farmacia_chedraui.csv"
CSV_OUTPUT = "./salida/data/2026/09_septiembre/scraping_detalle_chedraui.csv"
TIENDA = "Chedraui"

# Encabezados solicitados
FIELDNAMES = [
    "SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", 
    "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda"
]

# === Configurar Selenium ===
options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1920,1080")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

# === Preparar Archivo de Salida ===
os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
file_exists = os.path.exists(CSV_OUTPUT) and os.path.getsize(CSV_OUTPUT) > 0

# === Leer URLs de entrada ===
if not os.path.exists(CSV_INPUT):
    print(f"❌ No se encontró el archivo de entrada: {CSV_INPUT}")
    exit()

df_urls = pd.read_csv(CSV_INPUT)

# === Procesamiento ===
with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    if not file_exists:
        writer.writeheader()

    for index, row in df_urls.iterrows():
        url_producto = row["URL_PRODUCTO"]
        print(f"🔍 [{index+1}/{len(df_urls)}] Procesando: {url_producto}")

        try:
            # 1. Visitar la página para obtener el productId
            driver.get(url_producto)
            time.sleep(3) # Esperar a que cargue el JS de VTEX

            soup = BeautifulSoup(driver.page_source, "html.parser")
            scripts = soup.find_all("script")

            product_id = None
            for script in scripts:
                if script.string and "productId" in script.string:
                    # Buscamos el ID en el script de datos de VTEX
                    match = re.search(r'"productId":"?(\d+)"?', script.string)
                    if match:
                        product_id = match.group(1)
                        break

            if not product_id:
                print(f"   ⚠️ No se encontró productId en la página.")
                continue

            # 2. Consultar la API de Chedraui con el productId
            api_url = f"https://www.chedraui.com.mx/api/catalog_system/pub/products/search?fq=productId:{product_id}"
            response = requests.get(api_url, timeout=25)
            
            if response.status_code != 200 or not response.json():
                print(f"   ❌ Error API Chedraui (Status {response.status_code})")
                continue

            data = response.json()[0]
            
            # 3. Extraer información detallada
            nombre = data.get("productName", "")
            # SKU técnico
            sku = data.get("items", [{}])[0].get("itemId", "")
            # Imagen principal
            imagen = data.get("items", [{}])[0].get("images", [{}])[0].get("imageUrl", "")
            
            # Precios
            oferta_data = data.get("items", [{}])[0].get("sellers", [{}])[0].get("commertialOffer", {})
            precio_oferta = oferta_data.get("Price", 0.0)
            precio_actual = oferta_data.get("ListPrice", 0.0)

            # 4. Escribir registro
            writer.writerow({
                "SKU": sku,
                "URL_PRODUCTO": url_producto,
                "Producto": nombre,
                "Precio_Actual": f"{precio_actual:.2f}",
                "Precio_Oferta": f"{precio_oferta:.2f}",
                "URL_IMAGEN": imagen,
                "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Tienda": TIENDA
            })
            
            f.flush() # Guardar progreso en tiempo real
            print(f"   ✅ {sku} | ${precio_oferta:.2f}")

        except Exception as e:
            print(f"   💥 Error inesperado: {e}")

driver.quit()
print(f"\n✅ Scraping detallado de Chedraui completado. Archivo: {CSV_OUTPUT}")