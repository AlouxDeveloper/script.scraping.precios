import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import csv
import time
import os
import re
from typing import Optional, Dict, Any

# === Configuración de Archivos y Rutas ===
# Archivo CSV de entrada generado en la Fase 1 (URLs de producto)
CSV_INPUT = "./salida/urls/urls_productos_benavides.csv"
# Archivo CSV de salida con todos los detalles
CSV_OUTPUT = "./salida/data/2026/09_septiembre/scraping_detalle_benavides.csv" # RUTA ACTUALIZADA
TIENDA_NOMBRE = "2"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'es-ES,es;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Connection': 'keep-alive',
}

# Columnas de salida FINAL según lo solicitado
FIELDNAMES = [
    "SKU", 
    "URL_PRODUCTO",
    "PRODUCTO",
    "PRECIO_ACTUAL", # Precio REGULAR (más alto / tachado en HTML)
    "PRECIO_OFERTA", # Precio FINAL (más bajo / actual en HTML)
    "URL_IMAGEN",
    "FECHA",
    "TIENDA"
]

# === Utilidades de Precio y Formato ===
def _to_float(p: str) -> Optional[float]:
    """Convierte un string de precio (ej. '$1,234.56') a float. Devuelve None si no se puede."""
    if not p:
        return None
    try:
        txt = str(p).strip()
        txt = txt.replace("$", "").replace(",", "").replace("\xa0", " ").strip()
        m = re.search(r"(\d+(?:\.\d{1,2})?)", txt)
        if not m:
            return None
        return float(m.group(1))
    except:
        return None

def _fmt(val: Optional[float]) -> str:
    # MODIFICADO: Retorna el formato numérico sin el símbolo de dólar ($).
    """Formatea float a '1,234.56'. Si None, devuelve ''."""
    if val is None:
        return ""
    try:
        return "{:,.2f}".format(float(val))
    except:
        return str(val)

# === Funciones de Extracción Específicas para Benavides ===

def extraer_sku(soup: BeautifulSoup) -> str:
    """
    Extrae el SKU del producto.
    """
    try:
        # Selector CSS que apunta al valor dentro del contenedor de SKU
        el = soup.select_one(".product.attribute.sku .value")
        return el.get_text(strip=True) if el else ''
    except:
        return ''

def extraer_nombre(soup: BeautifulSoup) -> str:
    """Extrae el nombre completo (Marca + Producto + Presentación)."""
    try:
        titulo = soup.select_one("div.principal-attributes h1.product-substances")
        if not titulo:
            return ""
        marca = titulo.select_one("span.principal-title")
        nombre = titulo.select_one("span.product-name")
        presentacion = titulo.select_one("span.product-presentation")
        return " ".join([
            marca.text.strip() if marca else '',
            nombre.text.strip() if nombre else '',
            presentacion.text.strip() if presentacion else ''
        ]).strip()
    except:
        return ""

def extraer_precio_oferta_txt(soup: BeautifulSoup) -> str:
    """Extrae el precio FINAL (ENDPRICE) del producto principal."""
    try:
        # 1. Buscar primero el contenedor principal del precio.
        price_box = soup.select_one("div.product-info-price")
        
        if not price_box:
            # Si no se encuentra el contenedor principal, regresamos vacío.
            return '' 

        # 2. Buscar el span de precio final DENTRO de ese contenedor.
        # Es la primera etiqueta <span> con la clase 'price' dentro del contenedor principal.
        el = price_box.select_one(".price-final_price .price")
        
        return el.get_text(strip=True) if el else ''
    except:
        return ''

def extraer_precio_normal_txt(soup: BeautifulSoup) -> str:
    """Extrae el precio NORMAL (LISTPRICE) del producto principal (el tachado)."""
    try:
        # 1. Buscar primero el contenedor principal del precio.
        price_box = soup.select_one("div.product-info-price")
        
        if not price_box:
            return ''

        # 2. Buscar el precio anterior DENTRO de ese contenedor.
        el = price_box.select_one("span.old-price .price")
        
        return el.get_text(strip=True) if el else ''
    except:
        return ''

def extraer_url_imagen(soup: BeautifulSoup) -> str:
    """
    Extrae la URL de la imagen principal del producto.
    MODIFICADO: Prioriza el selector estático de la imagen placeholder inicial.
    """
    DOMAIN = "https://www.benavides.com.mx" # Dominio para corregir URLs relativas
    url_img = None
    
    try:
        # 1. Selector de mayor prioridad (basado en el HTML proporcionado): Imagen dentro del gallery-placeholder
        el_img_placeholder = soup.select_one('.gallery-placeholder__image')
        if el_img_placeholder:
            url_img = el_img_placeholder.get('src')
        
        # 2. Fallback: Intentar el link itemprop (también dentro del placeholder)
        if not url_img:
            el_link = soup.select_one('.gallery-placeholder link[itemprop="image"]')
            if el_link:
                url_img = el_link.get('href')

        # 3. Fallback: Contenedor activo (si el JS llegara a cargar, aunque es poco probable en scraping estático)
        if not url_img:
            el_contenedor_activo = soup.select_one('.fotorama__stage__frame.fotorama__active')
            if el_contenedor_activo and el_contenedor_activo.get('href'):
                url_img = el_contenedor_activo.get('href')


        # 4. Limpieza y Corrección de URL
        if url_img:
            # a. Eliminar parámetros de tamaño/cache si los hay
            cleaned_url = url_img.split('?')[0].strip()
            
            # b. Corregir URL relativa (si empieza con /)
            if cleaned_url.startswith('/') and not cleaned_url.startswith('//'):
                return f"{DOMAIN}{cleaned_url}"
            
            return cleaned_url
            
        return ''
    except:
        return ''

# === Función Principal ===
def main():
    """Lee URLs de Benavides y extrae detalles de cada página de producto."""
    
    if not os.path.exists(CSV_INPUT):
        print(f"Error: No se encontró el archivo de URLs de entrada '{CSV_INPUT}'.")
        return

    try:
        # 1. Leer las URLs del archivo CSV anterior
        df = pd.read_csv(CSV_INPUT, sep=';', encoding="utf-8")
        # Asegúrate de que las URLs de entrada no sean nulas o inválidas.
        urls_data = df.dropna(subset=['URL']).to_dict('records')
    except Exception as e:
        print(f"Error leyendo el archivo CSV: {e}.")
        return

    # 2. Cargar URLs ya procesadas para reanudar el trabajo
    procesadas = set()
    if os.path.exists(CSV_OUTPUT) and os.stat(CSV_OUTPUT).st_size > 0:
        try:
            prev = pd.read_csv(CSV_OUTPUT)
            if "URL_PRODUCTO" in prev.columns:
                procesadas = set(prev["URL_PRODUCTO"].astype(str).tolist())
            print(f"📂 Progreso cargado: {len(procesadas)} URLs ya procesadas.")
        except Exception as e:
            print(f"⚠️ Error cargando progreso previo, se comenzará desde cero: {e}")

    total_productos = len(urls_data)
    es_primera_escritura = not os.path.exists(CSV_OUTPUT) or os.stat(CSV_OUTPUT).st_size == 0
    
    # 3. Abrir el archivo de salida y comenzar el bucle
    os.makedirs(os.path.dirname(CSV_OUTPUT) or '.', exist_ok=True)

    with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=FIELDNAMES)

        # Escribe el encabezado si es la primera escritura
        if es_primera_escritura:
            writer.writeheader()

        # 4. Iterar sobre las URLs de producto
        for i, data in enumerate(urls_data, 1):
            url_producto = data['URL']
            
            if url_producto in procesadas:
                print(f"⏩ [{i}/{total_productos}] Saltando URL (ya procesada).")
                continue

            print(f"\n🔎 [{i}/{total_productos}] Extrayendo detalles de: {url_producto}")
            
            try:
                response = requests.get(url_producto, headers=HEADERS, timeout=25)
                
                if response.status_code != 200:
                    print(f"⚠️ HTTP {response.status_code} para {url_producto}.")
                    time.sleep(1.5)
                    continue

                soup = BeautifulSoup(response.content, 'lxml')

                # --- EXTRACCIÓN DE DATOS ---
                sku = extraer_sku(soup)
                nombre_completo = extraer_nombre(soup)
                url_imagen = extraer_url_imagen(soup)
                
                # Precios en texto sin formato
                precio_actual_txt = extraer_precio_oferta_txt(soup) # Precio FINAL (el más bajo)
                precio_normal_txt = extraer_precio_normal_txt(soup) # Precio NORMAL (el tachado)

                # Procesamiento de Precios (a float y lógica de corrección)
                val_actual = _to_float(precio_actual_txt)
                val_normal = _to_float(precio_normal_txt)

                # Lógica de corrección de precios
                if val_normal is None and val_actual is not None:
                    val_normal = val_actual # Si no hay precio normal (tachado), se asume que el precio actual es el regular.
                if val_normal is not None and val_actual is not None and val_normal < val_actual:
                    val_normal = val_actual # El precio normal no puede ser menor que el final, se corrige.
                
                # Mapeo a columnas de SALIDA:
                # PRECIO_ACTUAL (CSV) = Precio Regular (val_normal/tachado)
                # PRECIO_OFERTA (CSV) = Precio Final (val_actual/más bajo)
                out_actual = _fmt(val_normal)
                out_oferta = _fmt(val_actual) 
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Escribir la fila
                row = {
                    "SKU": sku,
                    "URL_PRODUCTO": url_producto,
                    "PRODUCTO": nombre_completo,
                    "PRECIO_ACTUAL": out_actual,
                    "PRECIO_OFERTA": out_oferta,
                    "URL_IMAGEN": url_imagen,
                    "FECHA": timestamp,
                    "TIENDA": TIENDA_NOMBRE
                }

                writer.writerow(row)
                output_file.flush() # <--- CLAVE PARA EL GUARDADO EN TIEMPO REAL
                print(f"✅ Guardado: SKU {sku} | Producto: {nombre_completo} | Precio Oferta: {out_oferta}")

                time.sleep(1.5) # Pausa entre productos

            except Exception as e:
                print(f"❌ Error inesperado al procesar {url_producto}: {e}")
                time.sleep(3) # Pausa larga después de un error

if __name__ == "__main__":
    main()