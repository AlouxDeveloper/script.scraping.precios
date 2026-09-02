import requests
from bs4 import BeautifulSoup
import csv
import time
import pandas as pd
import os # Necesario para verificar si el archivo CSV existe y manejar la cabecera

# --- Configuraciones ---
ARCHIVO_EXCEL = './data/urls_categorias_fesa.xlsx' # Asegúrate de que este archivo exista
NOMBRE_CSV_SALIDA = './salida/urls/urls_productos_fesa.csv' # Archivo de salida único
COLUMNA_URL_EXCEL = 'Url' # Nombre de la columna que contiene las URLs en tu Excel

# Cabeceras para simular un navegador
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Definición de columnas para el CSV
NOMBRES_COLUMNAS = ['Categoria_URL', 'Nombre', 'URL']

# --- Funciones de Utilidad ---

def escribir_csv_batch(datos, escribir_cabecera):
    """Escribe o añade datos al archivo CSV. Si es la primera escritura, incluye la cabecera."""
    try:
        # Crea la carpeta de salida si no existe
        directorio = os.path.dirname(NOMBRE_CSV_SALIDA)
        if directorio and not os.path.exists(directorio):
            os.makedirs(directorio)

        # Usamos modo 'a' (append) para añadir datos sin sobrescribir el progreso.
        with open(NOMBRE_CSV_SALIDA, mode='a', newline='', encoding='utf-8') as archivo_csv:
            writer = csv.DictWriter(archivo_csv, fieldnames=NOMBRES_COLUMNAS)
            
            if escribir_cabecera:
                writer.writeheader()
            
            writer.writerows(datos)
        return True
    except Exception as e:
        print(f"❌ ERROR al escribir en el CSV: {e}")
        return False

def scrapear_categoria_con_paginacion(url_base):
    """Scrapea todos los productos de una URL de categoría con paginación."""
    global datos_productos
    
    pagina_actual = 1
    productos_totales_categoria = 0
    
    print(f"\n========================================================")
    print(f"🚀 INICIANDO CATEGORÍA: {url_base}")
    print(f"========================================================")

    # El flag para saber si debemos escribir la cabecera en el CSV
    escribir_cabecera = not os.path.exists(NOMBRE_CSV_SALIDA)
    
    while True:
        # Construir la URL para la página actual (ej: .../oncologia.html?p=2)
        url_pagina = f"{url_base}?p={pagina_actual}"
        print(f"🌍 Scrapeando Página {pagina_actual} ({url_pagina})...")
        
        try:
            response = requests.get(url_pagina, headers=HEADERS, timeout=15) # Añadimos timeout
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # 1. Extraer los contenedores de productos
            contenedores_productos = soup.find_all('li', class_='item product product-item')
            
            if not contenedores_productos:
                print(f"🛑 Página {pagina_actual} no contiene productos. Finalizando esta categoría.")
                break 
                
            productos_encontrados_en_lote = []
            for producto in contenedores_productos:
                link_tag = producto.find('a', class_='product-item-link')
                
                if link_tag:
                    nombre_producto = link_tag.text.strip()
                    url_producto = link_tag.get('href')

                    # Añadir la URL de la categoría como referencia
                    productos_encontrados_en_lote.append({
                        'Categoria_URL': url_base,
                        'Nombre': nombre_producto,
                        'URL': url_producto
                    })
            
            # 2. Guardar el progreso en tiempo real (Modificación 2)
            if productos_encontrados_en_lote:
                escribir_csv_batch(productos_encontrados_en_lote, escribir_cabecera)
                
                # Desactivar la escritura de cabecera después de la primera escritura
                escribir_cabecera = False
                
                productos_totales_categoria += len(productos_encontrados_en_lote)
                print(f"✅ Productos extraídos de la Página {pagina_actual}: {len(productos_encontrados_en_lote)} (Total en categoría: {productos_totales_categoria})")

            # Avanzar a la siguiente página
            pagina_actual += 1
            
            # Pausa de cortesía
            time.sleep(1) # Aumentamos un poco la pausa por seguridad

        except requests.exceptions.RequestException as e:
            print(f"❌ Error HTTP/Conexión en {url_pagina}: {e}")
            break
            
    print(f"🏁 Categoría finalizada. Total de productos: {productos_totales_categoria}")


# --- Lógica Principal (Modificación 1) ---

if not os.path.exists(ARCHIVO_EXCEL):
    print(f"\nFATAL: El archivo Excel '{ARCHIVO_EXCEL}' no se encontró.")
else:
    try:
        # Leer el archivo Excel y obtener la lista de URLs
        df = pd.read_excel(ARCHIVO_EXCEL)
        urls_a_scrapear = df[COLUMNA_URL_EXCEL].dropna().unique().tolist()
        
        print(f"\n📂 Archivo Excel leído con {len(urls_a_scrapear)} URLs de categorías.")
        
        # Iterar sobre cada URL de categoría y scrapear sus productos
        for index, url in enumerate(urls_a_scrapear):
            print(f"\n--- PROCESANDO CATEGORÍA {index + 1} DE {len(urls_a_scrapear)} ---")
            scrapear_categoria_con_paginacion(url)
            time.sleep(2) # Pausa más larga entre categorías
            
        print("\n========================================================")
        print("🎉 PROCESO GLOBAL COMPLETADO.")
        print(f"Todos los resultados están en '{NOMBRE_CSV_SALIDA}'")
        print("========================================================")

    except KeyError:
        print(f"\nFATAL: La columna '{COLUMNA_URL_EXCEL}' no se encontró en el archivo Excel.")
    except Exception as e:
        print(f"\nFATAL: Ocurrió un error al leer el archivo Excel: {e}")