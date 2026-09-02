import pandas as pd
# Parche crítico: Usamos el requests camuflado que clona el protocolo TLS del navegador
from curl_cffi import requests
import time
import os
from datetime import datetime
from typing import Dict, Any, List

# --- Configuración de Archivos y Columnas ---
CSV_ENTRADA = "./salida/urls/urls_productos_sanpablo.csv"
CSV_OUTPUT_DETALLES = "./salida/data/2026/09_septiembre/scraping_detalles_sanpablo.csv"
COLUMNAS_ENTRADA = ["URL", "Producto"]
COLUMNAS_SALIDA_DETALLES = ["SKU", "URL_PRODUCTO", "PRODUCTO", "PRECIO_ACTUAL", 
                             "PRECIO_OFERTA", "URL_IMAGEN", "FECHA", "TIENDA"]
TIENDA_NOMBRE = "Farmacias San Pablo"

# --- Configuración de la API ---
BASE_API_URL_DETALLE = "https://api.farmaciasanpablo.com.mx/rest/v2/fsp/products/{sku}"
API_PARAMS_DETALLE = "?fields=code,name,price(formattedValue,DEFAULT),images(format,url,imageType),basePrice(FULL),potentialPromotions(FULL),additionalDescription,stock(DEFAULT),description,url&lang=es_MX&curr=MXN"

# Headers robustos imitando comportamiento real
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "es-MX,es;q=0.9",
    "Origin": "https://www.farmaciasanpablo.com.mx",
    "Referer": "https://www.farmaciasanpablo.com.mx/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

def extraer_sku_de_url(url_producto: str) -> str:
    """Extrae el SKU (código) del producto a partir de su URL."""
    try:
        return url_producto.split('/p/')[-1].strip()
    except:
        return None

def obtener_datos_producto(url_producto: str) -> Dict[str, Any]:
    """Consulta la API de detalle para un producto y extrae los campos requeridos."""
    sku = extraer_sku_de_url(url_producto)
    if not sku:
        print(f"    ⚠️ No se pudo extraer el SKU de la URL: {url_producto}")
        return None

    api_url = f"{BASE_API_URL_DETALLE.format(sku=sku)}{API_PARAMS_DETALLE}"
    
    try:
        # Inyectamos impersonate="chrome" para que herede las firmas SSL de Google Chrome reales
        respuesta = requests.get(api_url, headers=HEADERS, timeout=15, impersonate="chrome") 
        respuesta.raise_for_status() 
        datos = respuesta.json()

        # --- Extracción de datos del JSON ---
        precio_actual = datos.get('price', {}).get('value')
        precio_oferta = datos.get('basePrice', {}).get('value')
        
        # Resolución de imágenes
        url_imagen = None
        images = datos.get('images', [])
        for img in images:
            if img.get('format') == 'product':
                url_imagen = img.get('url')
                break
        if not url_imagen and images:
            for img in images:
                if img.get('imageType') == 'PRIMARY':
                    url_imagen = img.get('url')
                    break
        
        if precio_actual == precio_oferta or precio_oferta is None:
            precio_oferta = precio_actual

        registro = {
            "SKU": datos.get('code'),
            "URL_PRODUCTO": url_producto,
            "PRODUCTO": datos.get('name'),
            "PRECIO_ACTUAL": precio_actual,
            "PRECIO_OFERTA": precio_oferta,
            "URL_IMAGEN": url_imagen,
            "FECHA": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "TIENDA": TIENDA_NOMBRE
        }
        
        return registro

    except Exception as e:
        print(f"    ❌ Error de conexión/SSL para SKU {sku}: {e}. Omitiendo.")
        return None


def main():
    # 1. Verificar existencia de entrada y cargar datos
    if not os.path.exists(CSV_ENTRADA):
        print(f"Error: No se encontró el archivo de URLs de productos '{CSV_ENTRADA}'.")
        return

    try:
        # Forzar lectura explícita con separador de tu archivo original
        df_urls = pd.read_csv(CSV_ENTRADA, sep=';', encoding='utf-8')
        if "URL" not in df_urls.columns:
            # Reintento por si viene separado por comas
            df_urls = pd.read_csv(CSV_ENTRADA, sep=',', encoding='utf-8')
            
        urls_productos = df_urls["URL"].dropna().tolist()
    except Exception as e:
        print(f"Error al leer el archivo CSV de entrada: {e}")
        return
    
    # 2. Crear el directorio de salida si no existe
    output_dir = os.path.dirname(CSV_OUTPUT_DETALLES)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    # --- SISTEMA DE CONTROL DE AVANCE (Bypass de procesados) ---
    procesadas = set()
    if os.path.exists(CSV_OUTPUT_DETALLES) and os.stat(CSV_OUTPUT_DETALLES).st_size > 0:
        try:
            prev = pd.read_csv(CSV_OUTPUT_DETALLES)
            if "URL_PRODUCTO" in prev.columns:
                procesadas = set(prev["URL_PRODUCTO"].dropna().astype(str).tolist())
        except:
            pass

    print(f"Se encontraron **{len(urls_productos)}** productos en total.")
    print(f"📂 Historial: {len(procesadas)} ya se encuentran guardadas en el archivo final.")
    
    total_productos_extraidos = 0
    es_primera_escritura = not os.path.exists(CSV_OUTPUT_DETALLES)
    
    # 3. Iterar secuencialmente sobre los productos
    for i, url_producto in enumerate(urls_productos):
        if url_producto in procesadas:
            continue
            
        sku_actual = extraer_sku_de_url(url_producto)
        print(f"\n--- Procesando Producto {i+1} de {len(urls_productos)}: {sku_actual} ---")
        
        registro_detalle = obtener_datos_producto(url_producto)
        
        if registro_detalle:
            df_detalle = pd.DataFrame([registro_detalle])
            df_detalle = df_detalle[COLUMNAS_SALIDA_DETALLES] 
            
            # Guardado Incremental en Caliente
            df_detalle.to_csv(
                CSV_OUTPUT_DETALLES, 
                mode='a', 
                index=False, 
                sep=',', 
                encoding='utf-8', 
                header=es_primera_escritura
            )
            
            total_productos_extraidos += 1
            print(f"    💾 SKU {registro_detalle.get('SKU')} guardado con éxito. Total acumulado esta sesión: {total_productos_extraidos}.")
            es_primera_escritura = False 
            
            # Pausa táctica corta
            time.sleep(1)

    print(f"\n🎉 ¡Proceso finalizado! Sesión terminada con {total_productos_extraidos} nuevos registros guardados en '{CSV_OUTPUT_DETALLES}'.")

if __name__ == "__main__":
    main()