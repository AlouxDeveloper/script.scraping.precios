import os
import csv
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ========== Configuración ==========
EXCEL_CATEGORIAS = "./data/urls_categorias_comer.xlsx"
COLUMNA_EXCEL = "URL_CATEGORIA"
CSV_OUTPUT = "./salida/urls/agosto/urls_lacomer.csv"

def configurar_driver():
    opts = Options()
    # opts.add_argument("--headless") 
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)

def main():
    if not os.path.exists(EXCEL_CATEGORIAS):
        print(f"❌ No se encontró el Excel en {EXCEL_CATEGORIAS}"); return
    
    df_cat = pd.read_excel(EXCEL_CATEGORIAS)
    lista_urls = df_cat[COLUMNA_EXCEL].dropna().tolist()
    
    driver = configurar_driver()
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
    
    headers = ["Producto", "URL_PRODUCTO"]
    urls_vistas = set()
    file_exists = os.path.isfile(CSV_OUTPUT)
    
    try:
        with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists:
                writer.writeheader()

            for url_categoria in lista_urls:
                print(f"\n🚀 Navegando a categoría: {url_categoria}")
                driver.get(url_categoria)
                wait = WebDriverWait(driver, 25)
                
                pagina_actual = 1
                while True:
                    print(f"  📄 Procesando página {pagina_actual}...")
                    time.sleep(5) # Tiempo para que Angular renderice los productos

                    try:
                        # Esperar a que los enlaces de producto aparezcan
                        wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'detarticulo')]")))
                    except:
                        print("  ⚠️ No se detectaron productos en esta página.")
                        break

                    # --- Extracción de Datos de la Página Actual ---
                    # Buscamos los bloques de producto
                    enlaces_productos = driver.find_elements(By.XPATH, "//a[contains(@href, 'detarticulo')]")
                    
                    for link in enlaces_productos:
                        try:
                            url_prod = link.get_attribute("href")
                            
                            # El nombre está en el <strong> con itemprop="description"
                            # Lo buscamos dentro del elemento 'link' (a)
                            nombre_elem = link.find_element(By.XPATH, ".//strong[@itemprop='description']")
                            nombre = nombre_elem.text.strip()

                            if url_prod and url_prod not in urls_vistas:
                                writer.writerow({"Producto": nombre, "URL_PRODUCTO": url_prod})
                                urls_vistas.add(url_prod)
                                f.flush() # Guardar en tiempo real
                        except:
                            continue
                    
                    # --- Navegación a la Siguiente Página ---
                    try:
                        # Buscamos el botón Siguiente según la etiqueta proporcionada
                        # Usamos XPATH para identificar el texto "Siguiente" y el atributo ng-click
                        btn_siguiente = driver.find_element(By.XPATH, "//a[contains(@ng-click, 'pager.currentPage + 1') and contains(text(), 'Siguiente')]")
                        
                        if btn_siguiente.is_displayed():
                            print("  ➡️ Click en Siguiente...")
                            driver.execute_script("arguments[0].click();", btn_siguiente)
                            pagina_actual += 1
                            time.sleep(6) # Espera mayor para que Angular limpie y recargue el DOM
                        else:
                            break
                    except:
                        print("  🏁 Fin de la categoría (No se encontró botón Siguiente).")
                        break

    except Exception as e:
        print(f"❌ Error crítico: {e}")
    finally:
        print(f"\n🎯 Scraping finalizado. Total URLs: {len(urls_vistas)}")
        driver.quit()

if __name__ == "__main__":
    main()