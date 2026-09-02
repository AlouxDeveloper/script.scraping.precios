import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import pandas as pd
import csv
import os
import time

# === Configuración ===
EXCEL_ENTRADA = "./data/urls_categorias_walmart.xlsx"
COLUMNA_URL = "URL_Categoria"
CSV_OUTPUT = "./salida/urls/productos_walmart.csv"
ENCABEZADOS = ["Nombre", "URL"]
BASE_URL = "https://www.walmart.com.mx"
# Asegurar carpetas y archivo
os.makedirs(os.path.dirname(CSV_OUTPUT) or ".", exist_ok=True)
if not os.path.exists(CSV_OUTPUT):
    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ENCABEZADOS)
        writer.writeheader()

def iniciar_driver():
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1280,1000")
    # Versión de tu Chrome 143
    driver = uc.Chrome(options=options, version_main=143) 
    return driver

def main():
    try:
        df_cats = pd.read_excel(EXCEL_ENTRADA)
        urls = df_cats[COLUMNA_URL].dropna().tolist()
    except Exception as e:
        print(f"❌ Error leyendo Excel: {e}")
        return

    driver = iniciar_driver()

    try:
        for i, url_categoria in enumerate(urls, 1):
            # Log de categoría inicial
            print(f"\n🔍 [{i}/{len(urls)}] Buscando: {url_categoria}")
            driver.get(url_categoria)
            
            pagina_n = 1
            acumulado_categoria = 0
            
            while True:
                try:
                    # Esperar a que los elementos aparezcan
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[data-dca-name*="product_tile"]'))
                    )
                    
                    # Scroll para disparar carga dinámica
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                    time.sleep(1)

                    elementos = driver.find_elements(By.CSS_SELECTOR, 'div[data-dca-name*="product_tile"]')
                    productos_esta_pagina = 0

                    for el in elementos:
                        try:
                            tag_a = el.find_element(By.CSS_SELECTOR, "a[link-identifier]")
                            href = tag_a.get_attribute("href")
                            url_prod = href if href.startswith("http") else BASE_URL + href
                            
                            try:
                                nombre = el.find_element(By.CSS_SELECTOR, '[data-automation-id="product-title"]').text.strip()
                            except:
                                nombre = tag_a.get_attribute("innerText").strip()

                            if nombre and href:
                                with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
                                    writer = csv.DictWriter(f, fieldnames=ENCABEZADOS)
                                    writer.writerow({"Nombre": nombre, "URL": url_prod})
                                productos_esta_pagina += 1
                        except:
                            continue
                    
                    acumulado_categoria += productos_esta_pagina
                    # Log de progreso por página (como lo tenías antes)
                    print(f"   📄 Página {pagina_n}: {productos_esta_pagina} productos detectados (Total categoría: {acumulado_categoria})")

                    # Intentar pasar a la siguiente página
                    try:
                        boton_sig = driver.find_element(By.CSS_SELECTOR, 'a[data-testid="NextPage"]')
                        url_sig = boton_sig.get_attribute("href")
                        if url_sig:
                            driver.get(url_sig)
                            pagina_n += 1
                            time.sleep(2)
                        else:
                            break
                    except NoSuchElementException:
                        break

                except (TimeoutException, Exception):
                    break
            
            print(f"✅ Finalizada: {url_categoria} | Total: {acumulado_categoria}")

    except Exception as e:
        print(f"💥 Error crítico: {e}")
    finally:
        if driver:
            driver.quit()
        print(f"\n📦 Proceso masivo terminado. Resultados en: {CSV_OUTPUT}")

if __name__ == "__main__":
    main()