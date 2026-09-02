import os
import csv
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait as WW
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# === Configuración ===
# El archivo debe tener una columna llamada 'URL_CATEGORIA'
EXCEL_CATEGORIAS = "./data/urls_categorias_farmatodo.xlsx" 
CSV_OUTPUT = "./salida/data/marzo/scraping_urls_farmatodo.csv"

def configurar_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    # opts.add_argument("--headless=new") # Descomenta para correr sin ver la ventana
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

def main():
    if not os.path.exists(EXCEL_CATEGORIAS):
        print(f"❌ No se encontró el archivo de entrada: {EXCEL_CATEGORIAS}")
        return

    # Leer categorías (Funciona con Excel o CSV cambiando la función)
    try:
        df_cat = pd.read_excel(EXCEL_CATEGORIAS)
    except:
        df_cat = pd.read_csv(EXCEL_CATEGORIAS)
        
    lista_urls = df_cat['URL_CATEGORIA'].dropna().tolist()

    driver = configurar_driver()
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
    
    urls_vistas = set()

    try:
        with open(CSV_OUTPUT, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Producto", "URL_PRODUCTO"])
            writer.writeheader()

            for url_base in lista_urls:
                print(f"\n🚀 Explorando categoría: {url_base}")
                driver.get(url_base)
                num_pagina = 1
                
                # Espera inicial para carga de la plataforma VTEX
                time.sleep(7)

                while True:
                    print(f"  📄 Página {num_pagina}...")
                    
                    # 1. Scroll para activar la carga de elementos (Lazy Loading)
                    for _ in range(3):
                        driver.execute_script("window.scrollBy(0, 900);")
                        time.sleep(1.2)

                    # 2. Extraer productos con los selectores de Farmatodo
                    # Selector del enlace y contenedor
                    bloques = driver.find_elements(By.CSS_SELECTOR, "a.vtex-product-summary-2-x-clearLink")
                    nuevos_en_esta_vuelta = 0

                    for b in bloques:
                        try:
                            url_p = b.get_attribute("href")
                            # Selector del nombre dentro de la tarjeta
                            nombre_el = b.find_element(By.CLASS_NAME, "vtex-product-summary-2-x-brandName")
                            nombre_p = nombre_el.text.strip()

                            if url_p and url_p not in urls_vistas:
                                writer.writerow({
                                    "Producto": nombre_p,
                                    "URL_PRODUCTO": url_p
                                })
                                urls_vistas.add(url_p)
                                nuevos_en_esta_vuelta += 1
                        except:
                            continue

                    f.flush()
                    print(f"  ✅ {nuevos_en_esta_vuelta} productos nuevos. Total global: {len(urls_vistas)}")

                    # 3. Intentar cargar más productos
                    try:
                        # Ir al final para asegurar visibilidad del botón
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(3)

                        # Buscar botón "Mostrar más"
                        btn_mas = driver.find_elements(By.XPATH, "//div[contains(text(), 'Mostrar más')] | //button[contains(., 'Mostrar más')]")
                        
                        if btn_mas and btn_mas[0].is_displayed():
                            # Clic forzado con JS
                            driver.execute_script("arguments[0].click();", btn_mas[0])
                            num_pagina += 1
                            time.sleep(6) # Tiempo para que VTEX inyecte nuevos nodos
                        else:
                            print(f"  🏁 Fin de esta categoría.")
                            break
                    except:
                        break

    except Exception as e:
        print(f"❌ Error durante el proceso: {e}")
    finally:
        driver.quit()
        print(f"\n🎯 Scraping finalizado. URLs totales guardadas: {len(urls_vistas)}")

if __name__ == "__main__":
    main()