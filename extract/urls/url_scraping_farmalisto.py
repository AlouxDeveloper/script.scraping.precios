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

# === Configuración de Rutas de Axiom ===
CSV_OUTPUT = "./salida/urls/urls_productos_farmalisto.csv"
BASE_URL = "https://farmalisto.com.mx/2046-medicamentos?page={pagina}"

# Asegurar que existan las carpetas de salida
os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)

# === Detectar la última página procesada para reanudación automática ===
pagina_inicial = 1
if os.path.exists(CSV_OUTPUT) and os.stat(CSV_OUTPUT).st_size > 0:
    try:
        # Leemos el archivo actual para ver en qué página nos quedamos guardando
        df_prev = pd.read_csv(CSV_OUTPUT)
        if "Pagina_Origen" in df_prev.columns and not df_prev.empty:
            ultima_pagina_guardada = int(df_prev["Pagina_Origen"].max())
            pagina_inicial = ultima_pagina_guardada + 1
            print(f"🔄 Avance detectado: Reanudando automáticamente desde la página {pagina_inicial}")
    except Exception as e:
        print(f"⚠️ No se pudo leer el avance previo, iniciando desde la página 1. Detalle: {e}")

# === Bucle del Paginado (Abre y cierra el navegador por cada página de la lista) ===
# Definimos un rango alto (ej. 1000 páginas), el script se detendrá solo cuando ya no encuentre productos
for pagina in range(pagina_inicial, 1000):
    url_paginada = BASE_URL.format(pagina=pagina)
    print(f"\n🚀 [PÁGINA {pagina}] Conectando a: {url_paginada}")
    
    driver = None
    try:
        # Configuración del Driver de Selenium
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--log-level=3")  # Silenciar basura de la terminal
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        
        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 15)
        
        # Cargar página del listado
        driver.get(url_paginada)
        
        # Esperar a que al menos un contenedor de producto aparezca en pantalla
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".product-container")))
        except:
            print(f"🏁 Fin del catálogo o página vacía detectada en la página {pagina}. Terminando proceso.")
            break

        # Extraer todos los bloques de productos de la página actual
        bloques_productos = driver.find_elements(By.CSS_SELECTOR, ".product-container")
        print(f"📦 Se detectaron {len(bloques_productos)} productos en esta página.")
        
        if len(bloques_productos) == 0:
            print("🏁 Ya no hay más elementos que raspar. Fin del proceso.")
            break

        # Procesar los elementos encontrados en la página actual
        productos_pagina = []
        for bloque in bloques_productos:
            try:
                # Extraer URL y Nombre desde la etiqueta del título provista en tu HTML
                link_element = bloque.find_element(By.CSS_SELECTOR, ".product-title a")
                url_producto = link_element.get_attribute("href").strip()
                nombre_producto = link_element.get_attribute("innerText").strip()
                
                # Extraer el ID único del producto como SKU de respaldo desde el formulario del carrito
                try:
                    id_element = bloque.find_element(By.CSS_SELECTOR, "input[name='id_product']")
                    sku = id_element.get_attribute("value").strip()
                except:
                    sku = "N/A"

                # Armamos la fila con la columna de control de página para la reanudación
                item = {
                    "SKU": sku,
                    "URL": url_producto,
                    "Producto": nombre_producto,
                    "Pagina_Origen": pagina,
                    "Fecha_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                productos_pagina.append(item)
            except Exception as e:
                # Si un producto individual falla en la extracción, no detenemos el flujo de la página
                continue

        # === GUARDADO INCREMENTAL EN CALIENTE (Tiempo Real por página completada) ===
        if productos_pagina:
            file_exists = os.path.isfile(CSV_OUTPUT)
            with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as output_file:
                # Tomamos los nombres de las columnas del primer elemento extraído
                writer = csv.DictWriter(output_file, fieldnames=productos_pagina[0].keys())
                
                # Escribir cabeceras si el archivo es nuevo o está vacío
                if not file_exists or os.stat(CSV_OUTPUT).st_size == 0:
                    writer.writeheader()
                    
                # Escribimos en bloque todas las URLs recolectadas de esta página antes de cerrar el driver
                writer.writerows(productos_pagina)
                output_file.flush()
                
            print(f"💾 Guardados {len(productos_pagina)} productos de la página {pagina} correctamente en el CSV.")
        
    except Exception as e:
        print(f"❌ Error crítico procesando la página {pagina}: {e}")
        
    finally:
        # Se cierra la ventana obligatoriamente al acabar cada página del paginado
        if driver:
            driver.quit()
        # Pausa de cortesía de 2 segundos para enfriar la IP antes de abrir la siguiente página
        time.sleep(2)

print("\n🎉 ¡Catálogo completo de Farmalisto extraído con éxito!")