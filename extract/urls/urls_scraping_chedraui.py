import csv
import os
import time
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ========== Configuración ==========
EXCEL_CATEGORIAS = "./data/urls_categorias_chedraui.xlsx"
COLUMNA_EXCEL = "URL_CATEGORIA"
CSV_OUTPUT = "./salida/urls/agosto/urls_farmacia_chedraui.csv"


def configurar_driver():
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = uc.Chrome(options=options)
    return driver


def cerrar_modales_si_existen(driver):
    """Cierra popups de selección de código postal o cookies si aparecen."""
    selectores_cerrar = [
        "button[class*='close']",
        "button[aria-label='Close']",
        "div[class*='modal'] button",
        "button#onetrust-accept-btn-handler",
    ]
    for sel in selectores_cerrar:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(1)
        except Exception:
            pass


def scroll_dinamico(driver):
    """Realiza scroll progresivo para activar el lazy-loading de VTEX."""
    for fraction in [0.3, 0.6, 0.9, 1.0]:
        driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {fraction});")
        time.sleep(1.2)


def main():
    if not os.path.exists(EXCEL_CATEGORIAS):
        print(f"❌ No se encontró el Excel en {EXCEL_CATEGORIAS}")
        return

    df_cat = pd.read_excel(EXCEL_CATEGORIAS)
    lista_urls = df_cat[COLUMNA_EXCEL].dropna().unique().tolist()

    driver = configurar_driver()
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)

    headers = ["Producto", "URL_PRODUCTO"]
    urls_vistas = set()

    # Reanudar progreso si el CSV ya contiene datos
    if os.path.isfile(CSV_OUTPUT) and os.stat(CSV_OUTPUT).st_size > 0:
        try:
            df_prev = pd.read_csv(CSV_OUTPUT)
            urls_vistas = set(df_prev["URL_PRODUCTO"].dropna().tolist())
            print(f"ℹ️ Se cargaron {len(urls_vistas)} URLs ya procesadas del archivo existente.")
        except Exception:
            pass

    file_exists = os.path.isfile(CSV_OUTPUT) and os.stat(CSV_OUTPUT).st_size > 0

    try:
        with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_exists:
                writer.writeheader()

            for url_categoria in lista_urls:
                print(f"\n📂 CATEGORÍA: {url_categoria}")
                driver.get(url_categoria)
                time.sleep(4)
                cerrar_modales_si_existen(driver)

                wait = WebDriverWait(driver, 20)
                pagina_actual = 1

                while True:
                    print(f"  📄 Procesando página {pagina_actual}...")

                    scroll_dinamico(driver)

                    # Selector flexible que atrapa tarjetas de producto VTEX o enlaces terminados en /p
                    selector_productos = (
                        "a[class*='clearLink'], "
                        "section[class*='vtex-product-summary'] a, "
                        "a[href*='/p?'], a[href$='/p']"
                    )

                    try:
                        wait.until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector_productos))
                        )
                    except Exception:
                        print("  ⚠️ No se detectaron productos (posible fin de categoría o bloqueo).")
                        break

                    enlaces = driver.find_elements(By.CSS_SELECTOR, selector_productos)
                    nuevos = 0

                    for link in enlaces:
                        try:
                            url_p = link.get_attribute("href")
                            if not url_p or "/p" not in url_p:
                                continue

                            # Limpiar parámetros de tracking
                            url_p_limpia = url_p.split("?")[0]

                            if url_p_limpia in urls_vistas:
                                continue

                            # Extracción del nombre: busca elementos de título o toma el texto accesible
                            nombre = ""
                            try:
                                elem_nom = link.find_element(
                                    By.CSS_SELECTOR,
                                    "[class*='skuName'], [class*='productBrand'], h3, h2",
                                )
                                nombre = elem_nom.text.strip()
                            except Exception:
                                nombre = link.text.strip().split("\n")[0]

                            if not nombre:
                                # Fallback a partir del slug de la URL
                                nombre = url_p_limpia.rstrip("/p").split("/")[-1].replace("-", " ")

                            writer.writerow({
                                "Producto": nombre,
                                "URL_PRODUCTO": url_p_limpia,
                            })
                            urls_vistas.add(url_p_limpia)
                            nuevos += 1

                        except Exception:
                            continue

                    f.flush()
                    print(f"     ✅ {nuevos} productos nuevos en esta página.")

                    # Lógica de paginación o botón "Mostrar más / Siguiente"
                    btn_avanzar = None
                    selectores_next = [
                        "a[class*='ButtonNext']",
                        "button[class*='ButtonNext']",
                        "a[rel='next']",
                        "div[class*='showMoreButton'] button",
                        "button[class*='show-more']",
                    ]

                    for sel in selectores_next:
                        try:
                            candidato = driver.find_element(By.CSS_SELECTOR, sel)
                            if candidato.is_displayed() and candidato.is_enabled():
                                btn_avanzar = candidato
                                break
                        except Exception:
                            continue

                    if btn_avanzar:
                        try:
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block: 'center'});", btn_avanzar
                            )
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", btn_avanzar)
                            pagina_actual += 1
                            time.sleep(4)
                        except Exception as e:
                            print(f"  ℹ️ No se pudo hacer clic en siguiente página: {e}")
                            break
                    else:
                        print("  🏁 No hay más páginas disponibles en esta categoría.")
                        break

    except Exception as e:
        print(f"❌ Error crítico: {e}")
    finally:
        print(f"\n🎯 Proceso finalizado. Total acumulado en CSV: {len(urls_vistas)}")
        driver.quit()


if __name__ == "__main__":
    main()