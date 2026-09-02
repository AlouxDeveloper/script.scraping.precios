import time
import os
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
import csv 

# --- Configuración ---
CSV_URLS_CATEGORIA_ENTRADA = './data/urls_categorias_farmaciasgi.xlsx' 
CSV_URLS_PRODUCTO_SALIDA = './salida/urls/urls_productos_gi1.csv' 
COLUMNA_URL_ENTRADA = 'Url' 
COLUMNA_NOMBRE_CATEGORIA = 'Categoria' 

# SELECTORES ACTUALIZADOS
SELECTOR_PRODUCTO_LINK = 'a.ast-loop-product__link'
SELECTOR_PAGINACION_SIGUIENTE = 'a.next.page-numbers' 

def inicializar_archivo():
    directorio = os.path.dirname(CSV_URLS_PRODUCTO_SALIDA)
    if directorio and not os.path.exists(directorio):
        os.makedirs(directorio, exist_ok=True)
    
    if not os.path.exists(CSV_URLS_PRODUCTO_SALIDA):
        with open(CSV_URLS_PRODUCTO_SALIDA, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['URL_PRODUCTO', 'Categoria'])
            writer.writeheader()
        print(f"✅ Archivo creado: {CSV_URLS_PRODUCTO_SALIDA}")

def guardar_registro_inmediato(url_prod, nombre_cat):
    try:
        with open(CSV_URLS_PRODUCTO_SALIDA, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['URL_PRODUCTO','Categoria'])
            writer.writerow({
                'URL_PRODUCTO': url_prod,
                'Categoria': nombre_cat
            })
            f.flush()
    except Exception as e:
        print(f"❌ Error escribiendo en CSV: {e}")

# --- Proceso Principal ---
if __name__ == "__main__":
    inicializar_archivo()
    procesadas_esta_sesion = set()

    options = Options()
    # options.add_argument("--headless=new") 
    driver = webdriver.Chrome(options=options)

    try:
        df_entrada = pd.read_excel(CSV_URLS_CATEGORIA_ENTRADA)
        datos_categorias = df_entrada[[COLUMNA_URL_ENTRADA, COLUMNA_NOMBRE_CATEGORIA]].dropna().to_dict('records')

        for item in datos_categorias:
            url_cat = item[COLUMNA_URL_ENTRADA]
            nombre_cat = item[COLUMNA_NOMBRE_CATEGORIA]

            print(f"\n🔎 Entrando a: {nombre_cat} (URL: {url_cat})")
            driver.get(url_cat)
            time.sleep(5)

            pagina_actual = 1

            # 🚨 CAMBIO: Bucle infinito hasta que se acaben las páginas 🚨
            while True:
                # 1. Extraer productos de la página actual
                links = driver.find_elements(By.CSS_SELECTOR, SELECTOR_PRODUCTO_LINK)
                nuevos_en_esta_pagina = 0
                
                for link in links:
                    href = link.get_attribute('href')
                    if href and href not in procesadas_esta_sesion:
                        guardar_registro_inmediato(href, nombre_cat)
                        procesadas_esta_sesion.add(href)
                        nuevos_en_esta_pagina += 1

                print(f"   📄 Página {pagina_actual}: {nuevos_en_esta_pagina} productos nuevos guardados.")

                # 2. Intentar ir a la siguiente página
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                    
                    # Buscamos el botón de "Siguiente"
                    boton_siguiente = driver.find_elements(By.CSS_SELECTOR, SELECTOR_PAGINACION_SIGUIENTE)
                    
                    if len(boton_siguiente) > 0 and boton_siguiente[0].is_displayed():
                        driver.execute_script("arguments[0].click();", boton_siguiente[0])
                        pagina_actual += 1
                        time.sleep(5) # Espera para carga de la nueva página
                    else:
                        # Si no hay botón o no es visible, terminamos esta categoría
                        print(f"   🏁 Fin de categoría {nombre_cat}: No hay más páginas.")
                        break
                except Exception as e:
                    print(f"   🏁 Terminando categoría {nombre_cat} por falta de paginación o error: {e}")
                    break

    finally:
        driver.quit()
        print(f"\n🏁 FINALIZADO. Total de registros guardados: {len(procesadas_esta_sesion)}")