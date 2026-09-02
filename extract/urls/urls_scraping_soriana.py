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
EXCEL_CATEGORIAS = "./data/urls_categorias_soriana.xlsx" 
COLUMNA_EXCEL = "URL_CATEGORIA"
CSV_OUTPUT = "./salida/urls/urls_soriana.csv"

def configurar_driver():
    opts = Options()
    # opts.add_argument("--headless") # Descomenta para no ver la ventana
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    # Evitar detección básica
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def main():
    if not os.path.exists(EXCEL_CATEGORIAS):
        print(f"❌ No se encontró el Excel en {EXCEL_CATEGORIAS}"); return
    
    df_cat = pd.read_excel(EXCEL_CATEGORIAS)
    lista_urls = df_cat[COLUMNA_EXCEL].dropna().tolist()
    
    driver = configurar_driver()
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
    
    urls_vistas = set()
    file_exists = os.path.isfile(CSV_OUTPUT)
    
    try:
        # Abrimos en modo Append para no perder progreso
        with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Producto", "URL_PRODUCTO", "Categoria"])
            if not file_exists:
                writer.writeheader()

            for url_categoria in lista_urls:
                print(f"\n🚀 CATEGORÍA: {url_categoria}")
                driver.get(url_categoria)
                wait = WebDriverWait(driver, 20)
                
                pagina_actual = 1
                while True:
                    print(f"  📄 Procesando página {pagina_actual}...")
                    
                    # Esperar a que carguen los tiles de productos
                    try:
                        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "product-tile--link")))
                    except:
                        print("  ⚠️ No se cargaron productos. Saltando...")
                        break

                    # Scroll dinámico para cargar Lazy Load
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.4);")
                    time.sleep(2)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)

                    # Extracción de productos en la vista actual
                    enlaces = driver.find_elements(By.CLASS_NAME, "product-tile--link")
                    nuevos = 0
                    
                    for link in enlaces:
                        try:
                            url_p = link.get_attribute("href")
                            nombre = link.text.strip()

                            if url_p and nombre and url_p not in urls_vistas:
                                writer.writerow({
                                    "Producto": nombre, 
                                    "URL_PRODUCTO": url_p,
                                    "Categoria": url_categoria
                                })
                                urls_vistas.add(url_p)
                                nuevos += 1
                        except:
                            continue
                    
                    f.flush() # Guardado en tiempo real
                    print(f"     ✅ {nuevos} productos nuevos registrados.")

                    # --- Lógica de Paginación ---
                    try:
                        # Buscamos el botón específico que me pasaste
                        btn_siguiente = driver.find_element(By.CSS_SELECTOR, "button.slick-next.pagination")
                        
                        # Verificamos si es clickeable
                        if btn_siguiente.is_displayed():
                            print("  ➡️ Cargando siguiente página...")
                            # Usamos JS para el click por seguridad en Soriana
                            driver.execute_script("arguments[0].click();", btn_siguiente)
                            pagina_actual += 1
                            time.sleep(6) # Espera generosa para que el Grid se actualice
                        else:
                            print("  🏁 Fin de páginas (botón oculto).")
                            break
                    except:
                        print("  🏁 No se encontró botón 'Siguiente' adicional.")
                        break

    except Exception as e:
        print(f"❌ Error crítico: {e}")
    finally:
        print(f"\n🎯 Scraping finalizado. Total acumulado: {len(urls_vistas)}")
        driver.quit()

if __name__ == "__main__":
    main()