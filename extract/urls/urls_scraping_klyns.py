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
EXCEL_CATEGORIAS = "./data/urls_categorias_klyns.xlsx" 
CSV_OUTPUT = "./salida/urls/urls_klyns.csv"

def configurar_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

def main():
    if not os.path.exists(EXCEL_CATEGORIAS):
        print(f"❌ No se encontró el archivo de entrada: {EXCEL_CATEGORIAS}")
        return

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
                
                # Tiempo generoso para carga inicial
                time.sleep(10)

                while True:
                    print(f"  📄 Procesando carga de productos #{num_pagina}...")
                    
                    # 1. Scroll progresivo para asegurar que el DOM cargue nombres y fotos
                    for _ in range(4):
                        driver.execute_script("window.scrollBy(0, 1200);")
                        time.sleep(2)

                    # 2. Extraer productos
                    bloques = driver.find_elements(By.CSS_SELECTOR, "a.vtex-product-summary-2-x-clearLink")
                    nuevos_en_esta_vuelta = 0

                    for b in bloques:
                        try:
                            url_p = b.get_attribute("href")
                            nombre_el = b.find_element(By.CLASS_NAME, "vtex-product-summary-2-x-productBrandName")
                            nombre_p = nombre_el.text.strip()

                            if url_p and url_p not in urls_vistas:
                                writer.writerow({"Producto": nombre_p, "URL_PRODUCTO": url_p})
                                urls_vistas.add(url_p)
                                nuevos_en_esta_vuelta += 1
                        except:
                            continue

                    f.flush()
                    print(f"  ✅ {nuevos_en_esta_vuelta} productos nuevos. Total acumulado: {len(urls_vistas)}")

                    # 3. Lógica robusta para "Mostrar más"
                    try:
                        # Buscamos el botón
                        btn_xpath = "//button[contains(., 'Mostrar más')] | //div[contains(text(), 'Mostrar más')]"
                        botones = driver.find_elements(By.XPATH, btn_xpath)
                        
                        if botones and botones[0].is_displayed():
                            print("  ⏳ Botón detectado. Cargando más productos...")
                            
                            # Scroll hasta el botón para que sea clicable
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botones[0])
                            time.sleep(2)
                            
                            # Clic mediante JavaScript
                            driver.execute_script("arguments[0].click();", botones[0])
                            
                            # --- EL CAMBIO CLAVE: Espera extendida y validación ---
                            num_pagina += 1
                            print(f"  ⏳ Esperando 12 segundos a que el servidor responda...")
                            time.sleep(12) 
                            
                            # Pequeño movimiento extra para forzar el renderizado de los nuevos productos
                            driver.execute_script("window.scrollBy(0, 300);")
                            time.sleep(2)
                            driver.execute_script("window.scrollBy(0, -300);")
                            
                        else:
                            print(f"  🏁 No hay más botones de carga. Fin de categoría.")
                            break
                    except Exception as e:
                        print(f"  🏁 Finalizando categoría por: {str(e)[:50]}")
                        break

    except Exception as e:
        print(f"❌ Error crítico: {e}")
    finally:
        driver.quit()
        print(f"\n🎯 Proceso terminado. Total de productos únicos capturados: {len(urls_vistas)}")

if __name__ == "__main__":
    main()