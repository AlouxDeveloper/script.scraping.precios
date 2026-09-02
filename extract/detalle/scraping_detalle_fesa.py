import requests
from bs4 import BeautifulSoup
import csv
import time
import os
import pandas as pd
from datetime import datetime
import re 

# --- Importaciones de Selenium ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC 

# --- Configuraciones de Archivos ---
CSV_URLS_ENTRADA = './salida/urls/urls_productos_fesa.csv' 
CSV_DETALLE_SALIDA = './salida/data/2026/08_agosto/scraping_detalle_fesa.csv' 
COLUMNA_URL_ENTRADA = 'URL' 

# 🚨 ENCABEZADOS SOLICITADOS PARA EL ARCHIVO DE SALIDA 🚨
NOMBRES_COLUMNAS = [
    'SKU',
    'URL_PRODUCTO',
    'Producto',
    'Precio_Actual',
    'Precio_Oferta', 
    'URL_IMAGEN',
    'Fecha_Hora_Captura',
    'Tienda'
]

# ----------------------------------------------------------------------------------
# --- Funciones de Utilidad ---
# ----------------------------------------------------------------------------------

def _limpia_precio(tag_texto: str) -> str:
    """Limpia el formato del precio (quita $, , y normaliza a 2 decimales)."""
    if not tag_texto:
        return ""
    match = re.search(r'[\d,]+\.\d{2}', tag_texto.replace('$', '').strip())
    if match:
        t = match.group(0).replace(",", "").strip()
        try:
            return f"{float(t):.2f}"
        except ValueError:
            return ""
    return ""

def escribir_csv_progreso(fila: dict, escribir_cabecera: bool):
    """Escribe un solo registro al archivo CSV en modo append."""
    try:
        directorio = os.path.dirname(CSV_DETALLE_SALIDA)
        if directorio and not os.path.exists(directorio):
            os.makedirs(directorio, exist_ok=True)

        with open(CSV_DETALLE_SALIDA, mode='a', newline='', encoding='utf-8') as archivo_csv:
            writer = csv.DictWriter(archivo_csv, fieldnames=NOMBRES_COLUMNAS)
            
            if escribir_cabecera:
                writer.writeheader()
            
            writer.writerow(fila)
        return True
    except Exception as e:
        print(f"❌ ERROR al escribir en el CSV: {e}")
        return False

# ----------------------------------------------------------------------------------
# --- FUNCIONES DE EXTRACCIÓN SEPARADAS (ASUMIMOS QUE ESTÁN CORRECTAS) ---
# ----------------------------------------------------------------------------------

def _get_precio_actual_final(driver) -> str:
    """Obtiene el precio final de venta (el más bajo/precio actual)."""
    # ESTRATEGIA 1: Tomar el precio de Lealtad
    try:
        el_lealtad = driver.find_element(By.CSS_SELECTOR, 'p.lealtad.lealtad-desc-beneficio')
        return _limpia_precio(el_lealtad.text)
    except NoSuchElementException:
        pass

    # ESTRATEGIA 2: Tomar el precio de empleado
    try:
        el_especial = driver.find_element(By.CSS_SELECTOR, 'span.price-employees')
        return _limpia_precio(el_especial.text)
    except NoSuchElementException:
        pass
        
    return ""

def _get_precio_oferta_base(driver) -> str:
    """Obtiene el precio regular/base (el que debería ir tachado)."""
    
    # ESTRATEGIA 1: Precio tachado explícito (old-price)
    try:
        el_base_tachado = driver.find_element(By.CSS_SELECTOR, '.old-price .price-wrapper .price')
        return _limpia_precio(el_base_tachado.text)
    except NoSuchElementException:
        pass
        
    # ESTRATEGIA 2: Fallback al precio finalPrice genérico (el regular en Magento)
    try:
        el_base = driver.find_element(By.CSS_SELECTOR, 'span[data-price-type="finalPrice"] span.price')
        precio_regular_raw = el_base.get_attribute('aria-label')
        if precio_regular_raw:
            return _limpia_precio(precio_regular_raw)
        else:
            return _limpia_precio(el_base.text)
    except NoSuchElementException:
        pass

    return ""

def extraer_detalles_producto(driver, url_producto: str):
    
    sku = "N/A"
    nombre_producto = "N/A"
    url_imagen = ""
    
    precio_actual_salida = ""
    precio_oferta_salida = ""
    estado_especial = None
    
    try:
        driver.get(url_producto)
        
        # 🚨 ESPERAR A QUE EL CONTENEDOR DE PRECIOS/TÍTULO CARGUE 🚨
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'h1.page-title, div[data-role="priceBox"]'))
            )
            time.sleep(1.5) 
        except TimeoutException:
            pass 
        
        # --- MANEJO DE POP-UPS ---
        try:
            close_button = driver.find_element(By.CSS_SELECTOR, 'button.mfp-close')
            close_button.click()
            time.sleep(0.5)
        except NoSuchElementException:
            pass 

        # 1. Obtener Producto y SKU
        try:
            nombre_producto = driver.find_element(By.CSS_SELECTOR, 'h1.page-title').text.strip()
        except NoSuchElementException:
            pass
        
        # 🎯 CORRECCIÓN DEL SKU: Buscamos el elemento con itemprop="sku"
        try:
            # Selector basado en el HTML: <div class="value" itemprop="sku">
            sku_element = driver.find_element(By.CSS_SELECTOR, 'div[itemprop="sku"].value')
            sku = sku_element.text.strip()
            
            if not sku:
                # Fallback a la forma anterior si el nuevo selector está vacío
                form_tocart = driver.find_element(By.CSS_SELECTOR, 'form[data-role="tocart-form"]')
                sku = form_tocart.get_attribute('data-product-sku')
                
        except NoSuchElementException:
            # Si ambos fallan, el SKU sigue siendo "N/A"
            pass
        
        # 2. Manejo de estados especiales
        try:
            driver.find_element(By.CSS_SELECTOR, 'button.btn-cotizar')
            estado_especial = "COTIZACION REQUERIDA"
        except NoSuchElementException:
            try:
                driver.find_element(By.CSS_SELECTOR, 'div.product-info-stock-sku > div.stock.unavailable')
                estado_especial = "NO DISPONIBLE"
            except NoSuchElementException:
                pass
        
        if estado_especial:
            precio_actual_salida = estado_especial
        else:
            # 3. Extracción SEPARADA de Precios
            
            # 💡 Los nombres de las variables internas NO se invierten, solo su uso en la salida.
            precio_especial_limpio = _get_precio_actual_final(driver) # Es el precio BAJO
            precio_regular_limpio = _get_precio_oferta_base(driver)  # Es el precio ALTO
            
            # Convertir a float para comparar
            especial_float = float(precio_especial_limpio or 0)
            regular_float = float(precio_regular_limpio or 0)

            # --- LÓGICA DE ASIGNACIÓN FINAL (Invertida) ---
            
            if regular_float > 0 and especial_float > 0 and especial_float < regular_float:
                # 🎁 CASO 1: HAY AMBOS Y HAY DESCUENTO (Asignación Invertida)
                precio_actual_salida = f"${regular_float:.2f}"  # El precio ALTO va a Precio_Actual
                precio_oferta_salida = f"${especial_float:.2f}"  # El precio BAJO va a Precio_Oferta
            elif regular_float > 0:
                # 🚫 CASO 2: SOLO HAY PRECIO REGULAR
                precio_actual_salida = f"${regular_float:.2f}" 
                # Si no hay oferta, se deja vacío, o si es idéntico (según tu requerimiento)
                precio_oferta_salida = precio_actual_salida
            elif especial_float > 0:
                # 🚫 CASO 3: SOLO HAY PRECIO ESPECIAL (Si el precio regular falló)
                precio_actual_salida = f"${especial_float:.2f}" 
                precio_oferta_salida = precio_actual_salida

        # 4. Obtener URL de Imagen
        try:
            img_frame = driver.find_element(By.CSS_SELECTOR, 'div.fotorama__stage__frame')
            url_imagen = img_frame.get_attribute('href') 
            
            if not url_imagen:
                img_tag = img_frame.find_element(By.CSS_SELECTOR, 'img.fotorama__img')
                url_imagen = img_tag.get_attribute('src') or img_tag.get_attribute('data-src')
        except NoSuchElementException:
            url_imagen = ""
        
        
        # 5. Construir la Fila de Datos
        
        return {
            'SKU': sku,
            'URL_PRODUCTO': url_producto,
            'Producto': nombre_producto,
            'Precio_Actual': precio_actual_salida, # <-- Precio Regular/Alto
            'Precio_Oferta': precio_oferta_salida, # <-- Precio Especial/Bajo
            'URL_IMAGEN': url_imagen,
            'Fecha_Hora_Captura': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'Tienda': "5"
        }

    except Exception as e:
        print(f"❌ Error general al extraer datos del producto {url_producto}: {e}")
        return None

# ----------------------------------------------------------------------------------
# --- Lógica Principal de Control (Manejo de Selenium) ---
# ----------------------------------------------------------------------------------

if not os.path.exists(CSV_URLS_ENTRADA):
    print(f"\nFATAL: El archivo de URLs de entrada '{CSV_URLS_ENTRADA}' no se encontró.")
else:
    # 🚨 INICIALIZACIÓN DE SELENIUM 🚨
    options = Options()
    options.add_argument("--headless=new") 
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    driver = None
    try:
        driver = webdriver.Chrome(options=options)

        df = pd.read_csv(CSV_URLS_ENTRADA, dtype=str)
        urls_productos = df[COLUMNA_URL_ENTRADA].dropna().unique().tolist()
        
        print(f"\n📂 Archivo de URLs leído. Se procesarán {len(urls_productos)} productos usando Selenium.")
        
        escribir_cabecera = not os.path.exists(CSV_DETALLE_SALIDA)
        productos_procesados = 0
        
        for index, url_producto in enumerate(urls_productos, 1):
            print(f"\n--- 🔎 Procesando Producto {index} de {len(urls_productos)}: {url_producto[:80]}... ---")
            
            detalle = extraer_detalles_producto(driver, url_producto)
            
            if detalle and detalle['Producto'] != 'N/A':
                escribir_csv_progreso(detalle, escribir_cabecera)
                escribir_cabecera = False 
                productos_procesados += 1
                
                print(f"✅ DETALLE GUARDADO: {detalle['Producto']} | Actual (Regular): {detalle['Precio_Actual']} | Oferta (Especial): {detalle['Precio_Oferta']} | Imagen: {bool(detalle['URL_IMAGEN'])}")
            else:
                fila_vacia = {col: '' for col in NOMBRES_COLUMNAS}
                fila_vacia['URL_PRODUCTO'] = url_producto
                fila_vacia['Fecha_Hora_Captura'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                fila_vacia['Tienda'] = 'Farmacias FESA'
                escribir_csv_progreso(fila_vacia, escribir_cabecera)
                escribir_cabecera = False
                print(f"⚠️ Omisión: Fallo al obtener el detalle del producto en {url_producto}. Se registró una fila vacía.")
            
            time.sleep(0.5) 
            
    except Exception as e:
        print(f"\nFATAL: Ocurrió un error en el bucle principal o al leer el CSV: {e}")

    finally:
        if driver:
            driver.quit()
        
        print("\n========================================================")
        print("🎉 PROCESO DE EXTRACCIÓN DE DETALLES FINALIZADO.")
        print(f"Total de productos procesados y registrados: {productos_procesados}")
        print(f"Resultados guardados en: '{CSV_DETALLE_SALIDA}'")
        print("========================================================")