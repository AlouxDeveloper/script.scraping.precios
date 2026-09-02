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
EXCEL_CATEGORIAS = "./data/urls_categorias_yza.xlsx" 
COLUMNA_EXCEL = "URL_CATEGORIA"
CSV_OUTPUT = "./salida/urls/urls_yza.csv"

def configurar_driver():
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def main():
    if not os.path.exists(EXCEL_CATEGORIAS):
        print(f"❌ No se encontró el Excel: {EXCEL_CATEGORIAS}"); return
    
    df_cat = pd.read_excel(EXCEL_CATEGORIAS)
    lista_urls = df_cat[COLUMNA_EXCEL].dropna().tolist()
    
    driver = configurar_driver()
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
    
    urls_vistas = set()
    
    try:
        # Abrimos para escribir desde cero o añadir
        with open(CSV_OUTPUT, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["Producto", "URL_PRODUCTO"])
            writer.writeheader()

            for url_categoria in lista_urls:
                print(f"\n🚀 Categoría: {url_categoria}")
                driver.get(url_categoria)
                wait = WebDriverWait(driver, 15)

                while True:
                    time.sleep(4) # Espera a que el grid cargue
                    
                    # 1. Extraer productos de la página actual
                    try:
                        # Buscamos los enlaces con clase 'link' que mencionaste
                        productos = driver.find_elements(By.CSS_SELECTOR, "a.link")
                        count_pag = 0
                        for p in productos:
                            nombre = p.text.strip()
                            link = p.get_attribute("href")
                            
                            # Filtro para asegurar que sea link de producto (contiene .html)
                            if link and ".html" in link and nombre and link not in urls_vistas:
                                writer.writerow({"Producto": nombre, "URL_PRODUCTO": link})
                                urls_vistas.add(link)
                                count_pag += 1
                        
                        f.flush()
                        print(f"   ✅ Extraídos {count_pag} productos.")
                    except Exception as e:
                        print(f"   ⚠️ Error extrayendo productos: {e}")

                    # 2. Lógica de Paginación (Buscar el siguiente número)
                    try:
                        # Buscamos el botón que es la página actual
                        pag_actual_elem = driver.find_element(By.CSS_SELECTOR, "button.current-page")
                        # El siguiente botón de página suele ser el hermano siguiente (sibling)
                        # o el que tiene el número inmediatamente superior
                        
                        # Intentamos encontrar el siguiente botón de número que no sea la actual y no sea 'dots'
                        botones_pag = driver.find_elements(By.CSS_SELECTOR, ".pagination button.btn-page")
                        btn_siguiente = None
                        
                        encontrado_actual = False
                        for btn in botones_pag:
                            if "current-page" in btn.get_attribute("class"):
                                encontrado_actual = True
                                continue
                            if encontrado_actual and "dots" not in btn.get_attribute("class"):
                                btn_siguiente = btn
                                break
                        
                        if btn_siguiente:
                            num_pag = btn_siguiente.text.strip()
                            print(f"   ➡️ Saltando a página {num_pag}...")
                            driver.execute_script("arguments[0].click();", btn_siguiente)
                            # Esperar a que la página actual cambie (indicativo de carga AJAX)
                            time.sleep(2)
                        else:
                            print("   🏁 No hay más páginas en esta categoría.")
                            break
                    except:
                        print("   🏁 No se encontró control de paginación.")
                        break

    except Exception as e:
        print(f"❌ Error crítico: {e}")
    finally:
        print(f"\n🎯 Proceso terminado. Total URLs: {len(urls_vistas)}")
        driver.quit()

if __name__ == "__main__":
    main()