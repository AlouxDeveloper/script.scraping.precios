import csv
import os
import time
import requests
from bs4 import BeautifulSoup
import re
import datetime # Para la columna FECHA
import urllib.parse 

# --- CONFIGURACIÓN DE ARCHIVOS ---
# Archivo de entrada: CSV generado por el scraper de listado
CSV_INPUT_PATH = './salida/urls/urls_productos_ahorrro.csv' 
# Archivo de salida: CSV de detalles de productos
CSV_OUTPUT_PATH = './salida/data/2026/09_septiembre/scraping_detalles_fahorro.csv' 

# Asegurar que el directorio de salida exista
os.makedirs(os.path.dirname(CSV_OUTPUT_PATH), exist_ok=True)

# --- CONFIGURACIÓN GENERAL ---
URL_BASE = "https://www.fahorro.com"
TIENDA = "3"

HEADERS = {
    'User-Agent': 'Mozilla/50 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html',
    'Accept-Language': 'es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3',
}

# --- FUNCIÓN DE EXTRACCIÓN DE DETALLES ---

def limpiar_precio(precio_raw):
    """Limpia y normaliza el texto de precio, eliminando símbolos y comas."""
    if precio_raw:
        # Busca el span que contiene el precio y sus decimales, ignorando la moneda y tags internos.
        # Esto es necesario para eliminar posibles tags <font> o <span> anidados
        price_tag = BeautifulSoup(precio_raw, 'html.parser').find('span', class_='price')
        if price_tag:
            # Obtiene el texto completo y lo normaliza
            full_price_text = price_tag.get_text(strip=True)
            
            # Limpia de cualquier carácter que no sea dígito, coma o punto.
            precio_limpio = re.sub(r'[^\d,.]', '', full_price_text)
            
            # Formato final
            return precio_limpio.replace(',', '.') 
    return ""

def extraer_detalles_producto(product_url, writer):
    """
    Visita la URL de un producto, extrae SKU, nombre, precios, imagen, y registra los detalles.
    """
    
    print(f"[INFO] Procesando: {product_url}")
    
    # Inicializar datos vacíos
    producto_data = {
        'SKU': '',
        'URL_PRODUCTO': product_url,
        'PRODUCTO': '',
        'PRECIO_ACTUAL': '',
        'PRECIO_OFERTA': '',
        'URL_IMAGEN': '',
        'FECHA': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'TIENDA': TIENDA
    }

    try:
        response = requests.get(product_url, headers=HEADERS, timeout=30)
        
        if response.status_code != 200:
            print(f"   [ERROR] Solicitud fallida (Status: {response.status_code}).")
            return
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # --- 1. SKU ---
        # Buscamos la fila de la tabla de detalles que contiene 'SKU'
        sku_tag = soup.find('th', string=lambda t: t and 'SKU' in t)
        if sku_tag:
            # El SKU está en la celda 'td' subsiguiente
            sku_value_tag = sku_tag.find_next_sibling('td', class_='data')
            if sku_value_tag:
                producto_data['SKU'] = sku_value_tag.get_text(strip=True)

        # --- 2. PRODUCTO (Nombre) ---
        # <h1 class="page-title"><span class="base" ... >[NOMBRE]</span></h1>
        nombre_tag = soup.select_one('.page-title-wrapper.product .base')
        if nombre_tag:
            producto_data['PRODUCTO'] = nombre_tag.get_text(strip=True)

        # --- 3. PRECIOS (CORREGIDO Y REFORZADO) ---
        
        # Contenedor principal de precios del producto
        main_price_box = soup.select_one('.product-info-main .price-box')
        
        if main_price_box:
            # 3a. Intentamos encontrar el PRECIO DE OFERTA/FINAL (.special-price)
            precio_oferta_tag = main_price_box.select_one('.special-price')
            
            if precio_oferta_tag:
                # Caso A: PROMOCIÓN ENCONTRADA
                
                # PRECIO_OFERTA: Es el precio final dentro de .special-price
                precio_final_tag = precio_oferta_tag.select_one('.price-wrapper')
                if precio_final_tag:
                    producto_data['PRECIO_OFERTA'] = limpiar_precio(str(precio_final_tag))
                
                # PRECIO_ACTUAL: Es el precio tachado (.old-price)
                precio_actual_tag = main_price_box.select_one('.old-price')
                if precio_actual_tag:
                    precio_habitual_tag = precio_actual_tag.select_one('.price-wrapper')
                    if precio_habitual_tag:
                         # El precio normal (old-price) es el PRECIO_ACTUAL
                        producto_data['PRECIO_ACTUAL'] = limpiar_precio(str(precio_habitual_tag))
                
            else:
                # Caso B: SIN PROMOCIÓN (COPIA EL PRECIO ÚNICO A AMBAS COLUMNAS)
                
                # Buscamos directamente el price-wrapper que contiene el precio único visible
                precio_unico_tag = main_price_box.select_one('.price-final_price > .price-container > .price-wrapper')
                
                if precio_unico_tag:
                    # Si solo hay un precio, se registra como PRECIO_ACTUAL y se COPIA a PRECIO_OFERTA
                    precio_unico_limpio = limpiar_precio(str(precio_unico_tag))
                    producto_data['PRECIO_ACTUAL'] = precio_unico_limpio
                    producto_data['PRECIO_OFERTA'] = precio_unico_limpio
        
        # --- 4. URL IMAGEN (CORRECCIÓN APLICADA: Búsqueda por patrón de URL) ---
        
        # Estrategia: Buscar el primer tag <img> cuyo 'src' contenga '/media/catalog/product/'
        img_tag = soup.find('img', src=lambda src: src and '/media/catalog/product/' in src)
        
        if img_tag:
            # Tomamos el atributo 'src'
            img_src = img_tag.get('src')
            if img_src:
                # Usamos urlsplit para obtener la URL limpia sin parámetros de redimensionamiento
                parsed_url = urllib.parse.urlsplit(img_src)
                # Reconstruimos solo esquema, host y path
                clean_url = parsed_url.scheme + "://" + parsed_url.netloc + parsed_url.path
                
                producto_data['URL_IMAGEN'] = clean_url

        # --- 5. Registro Incremental ---
        writer.writerow([
            producto_data['SKU'],
            producto_data['URL_PRODUCTO'],
            producto_data['PRODUCTO'],
            producto_data['PRECIO_ACTUAL'],
            producto_data['PRECIO_OFERTA'],
            producto_data['URL_IMAGEN'],
            producto_data['FECHA'],
            producto_data['TIENDA']
        ])
        print(f"   [ÉXITO] Producto '{producto_data['PRODUCTO']}' ({producto_data['SKU']}) registrado.")
        
    except requests.exceptions.RequestException as e:
        print(f"   [ERROR] Fallo de conexión o timeout: {e}")
    except Exception as e:
        print(f"   [ERROR] Fallo de extracción en la URL. {e}")


# --- FUNCIÓN PRINCIPAL MAIN ---

def main():
    
    print("--- INICIANDO EXTRACCIÓN DE DETALLES DE PRODUCTOS DE FARMACIAS DEL AHORRO ---")
    
    # 1. Leer URLs del CSV de entrada (producto)
    urls_a_procesar = []
    
    try:
        with open(CSV_INPUT_PATH, 'r', newline='', encoding='utf-8') as f:
            lector = csv.reader(f)
            # Intentar determinar la cabecera (se asume que la primera columna es 'URL_PRODUCTO')
            header = next(lector) 
            url_index = header.index('URL_PRODUCTO') if 'URL_PRODUCTO' in header else 0 
            
            for row in lector:
                if len(row) > url_index:
                    urls_a_procesar.append(row[url_index])
        
        print(f"✔️ {len(urls_a_procesar)} URLs de productos a procesar leídas de {CSV_INPUT_PATH}.")
        
    except FileNotFoundError:
        print(f"❌ ERROR: Archivo de entrada ({CSV_INPUT_PATH}) no encontrado. Asegúrese de ejecutar el scraper de listado primero.")
        return
    except Exception as e:
        print(f"❌ ERROR: Fallo al leer el archivo CSV de entrada: {e}")
        return
        
    # 2. Open output CSV in append mode (incremental) and write header
    write_header = not os.path.exists(CSV_OUTPUT_PATH) or os.stat(CSV_OUTPUT_PATH).st_size == 0
    
    try:
        with open(CSV_OUTPUT_PATH, 'a', newline='', encoding='utf-8') as csv_file:
            csv_writer = csv.writer(csv_file)
            
            # Definición de la cabecera final
            if write_header:
                 csv_writer.writerow(['SKU','URL_PRODUCTO',  'PRODUCTO', 'PRECIO_ACTUAL', 'PRECIO_OFERTA', 'URL_IMAGEN', 'FECHA', 'TIENDA'])

            # 3. Iterar y extraer detalles
            for url in urls_a_procesar:
                extraer_detalles_producto(url, csv_writer)
                time.sleep(random.uniform(1, 3)) # Pausa para ser respetuoso con el servidor

    except KeyboardInterrupt:
        print("\n\n🚨 Proceso interrumpido por el usuario (Ctrl+C).")
        
    except Exception as e:
        print(f"\n\n❌ FATAL ERROR: {e}")
        
    finally:
        print(f"\n--- PROCESO FINALIZADO ---")
        print(f"Revisa el archivo de salida: **{CSV_OUTPUT_PATH}**")

if __name__ == '__main__':
    # Necesitamos importar random aquí para el uso en time.sleep()
    import random 
    main()
