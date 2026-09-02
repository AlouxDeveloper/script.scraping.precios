import time
import os
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import csv 
from datetime import datetime

# --- CONFIGURACIÓN ---
CSV_URLS_PRODUCTOS_ENTRADA = './salida/urls/urls_productos_gi1.csv'
CSV_DATOS_FINAL_SALIDA = './salida/data/2026/08_agosto/scraping_detalles_gi.csv'
TIENDA = "Farmacias Gi"

def inicializar_csv_final():
    """Crea la carpeta y el archivo final con cabeceras si no existe."""
    directorio = os.path.dirname(CSV_DATOS_FINAL_SALIDA)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio, exist_ok=True)
    
    if not os.path.exists(CSV_DATOS_FINAL_SALIDA):
        with open(CSV_DATOS_FINAL_SALIDA, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'SKU', 'URL_PRODUCTO', 'Producto', 'Precio_Actual', 
                'Precio_Oferta', 'URL_IMAGEN', 'Fecha_Hora_Captura', 'Tienda'
            ])
            writer.writeheader()
        print(f"✅ Archivo final creado: {CSV_DATOS_FINAL_SALIDA}")

def obtener_ya_procesados():
    """Para no repetir productos si el script se detiene."""
    if os.path.exists(CSV_DATOS_FINAL_SALIDA):
        try:
            df = pd.read_csv(CSV_DATOS_FINAL_SALIDA, usecols=['URL_PRODUCTO'])
            return set(df['URL_PRODUCTO'].tolist())
        except:
            return set()
    return set()

def guardar_datos_producto(datos):
    """Escribe los datos en el CSV final inmediatamente."""
    with open(CSV_DATOS_FINAL_SALIDA, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=datos.keys())
        writer.writerow(datos)
        f.flush()

# --- LÓGICA PRINCIPAL ---
if __name__ == "__main__":
    inicializar_csv_final()
    urls_procesadas = obtener_ya_procesados()
    
    # Cargar URLs del script anterior
    if not os.path.exists(CSV_URLS_PRODUCTOS_ENTRADA):
        print(f"❌ No se encontró el archivo de entrada: {CSV_URLS_PRODUCTOS_ENTRADA}")
        exit()

    df_urls = pd.read_csv(CSV_URLS_PRODUCTOS_ENTRADA)
    lista_urls = df_urls['URL_PRODUCTO'].tolist()

    print(f"📦 Total de productos a procesar: {len(lista_urls)}")
    print(f"⏭️ Saltando {len(urls_procesadas)} ya procesados.")

    options = Options()
    # options.add_argument("--headless=new") 
    driver = webdriver.Chrome(options=options)

    try:
        for i, url in enumerate(lista_urls, 1):
            if url in urls_procesadas:
                continue

            print(f"\n🔎 [{i}/{len(lista_urls)}] Procesando: {url}")
            
            try:
                driver.get(url)
                time.sleep(3) # Espera de carga

                # Diccionario base de datos
                datos = {
                    'SKU': 'N/A',
                    'URL_PRODUCTO': url,
                    'Producto': 'N/A',
                    'Precio_Actual': '0.00',
                    'Precio_Oferta': '0.00',
                    'URL_IMAGEN': 'N/A',
                    'Fecha_Hora_Captura': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'Tienda': TIENDA
                }

                # --- 1. EXTRACCIÓN DEL SKU ---
                try:
                    sku_elem = driver.find_element(By.CSS_SELECTOR, 'span.sku')
                    datos['SKU'] = sku_elem.text.strip()
                    print(f"   🆔 SKU: {datos['SKU']}")
                except NoSuchElementException:
                    print("   ⚠️ No se encontró SKU")

                # --- AQUÍ AGREGAREMOS LOS SIGUIENTES DATOS ---
                try:
                    nombre_elem = driver.find_element(By.CSS_SELECTOR, 'h1.product_title')
                    datos['Producto'] = nombre_elem.text.strip()
                    print(f"   🏷️ Producto: {datos['Producto']}")
                except NoSuchElementException:
                    print("   ⚠️ No se encontró Producto")
                    
                    
                # --- 3. EXTRACCIÓN DE PRECIOS (Lógica de Igualdad) ---
                try:
                    # Buscamos el contenedor de precio que mencionaste
                    # WooCommerce suele envolverlo en un párrafo o span con clase 'price'
                    price_container = driver.find_element(By.CSS_SELECTOR, 'p.price')
                    
                    try:
                        # Intentamos detectar si hay un precio rebajado (etiqueta <ins>)
                        # En WooCommerce: <del> es el tachado, <ins> es el nuevo.
                        precio_ins = price_container.find_element(By.CSS_SELECTOR, 'ins .woocommerce-Price-amount')
                        precio_del = price_container.find_element(By.CSS_SELECTOR, 'del .woocommerce-Price-amount')
                        
                        # Si existen ambos, hay oferta
                        datos['Precio_Actual'] = precio_del.text.replace('$', '').replace(',', '').strip()
                        datos['Precio_Oferta'] = precio_ins.text.replace('$', '').replace(',', '').strip()
                        print(f"   💰 Oferta detectada: {datos['Precio_Actual']} -> {datos['Precio_Oferta']}")
                        
                    except NoSuchElementException:
                        # Si NO hay <ins>, buscamos el precio único
                        precio_unico_elem = price_container.find_element(By.CSS_SELECTOR, '.woocommerce-Price-amount')
                        valor_limpio = precio_unico_elem.text.replace('$', '').replace(',', '').strip()
                        
                        datos['Precio_Actual'] = valor_limpio
                        datos['Precio_Oferta'] = valor_limpio # Se igualan según tu instrucción
                        print(f"   💰 Precio regular (igualado): {datos['Precio_Actual']}")

                except NoSuchElementException:
                    print("   ⚠️ No se encontró el bloque de precios")
                    datos['Precio_Actual'] = "0.00"
                    datos['Precio_Oferta'] = "0.00"
                    
                    
                try:
                    # Intentamos primero con tu selector específico
                    try:
                        imagen_elem = driver.find_element(By.CSS_SELECTOR, 'img.zoomImg')
                        datos['URL_IMAGEN'] = imagen_elem.get_attribute('src')
                    except NoSuchElementException:
                        # Si no existe zoomImg, usamos la imagen principal de WooCommerce/Astra
                        imagen_elem = driver.find_element(By.CSS_SELECTOR, 'img.wp-post-image')
                        datos['URL_IMAGEN'] = imagen_elem.get_attribute('src')
                    
                    print(f"   🖼️ Imagen: {datos['URL_IMAGEN']}")
                except NoSuchElementException:
                    print("   ⚠️ No se encontró la imagen del producto")
                    datos['URL_IMAGEN'] = "N/A"    
                    
                
                # Guardar inmediatamente
                guardar_datos_producto(datos)
                urls_procesadas.add(url)

            except Exception as e:
                print(f"   ❌ Error al entrar al producto: {e}")
                continue

    finally:
        driver.quit()
        print("\n🏁 Proceso de extracción de detalles finalizado.")