import os
import csv
import time
import re
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# === Configuración ===
CSV_INPUT    = "./salida/urls/urls_yza.csv"
CSV_OUTPUT   = "./salida/data/2026/08_agosto/scraping_detalle_yza.csv"
TIENDA       = "Farmacias Yza"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "es-MX,es;q=0.9",
    "Referer": "https://www.yza.mx/",
}

CSV_FIELDS = ["SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda"]

def clean_price(txt: str) -> str:
    if not txt: return "0.00"
    t = txt.replace("\xa0", " ").replace(",", "").replace("$", "").strip()
    m = re.search(r"(\d+(?:\.\d{1,2})?)", t)
    return m.group(1) if m else "0.00"

def get_soup(session: requests.Session, url: str) -> BeautifulSoup | None:
    try:
        r = session.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200: return None
        return BeautifulSoup(r.text, "html.parser")
    except:
        return None

def main():
    if not os.path.exists(CSV_INPUT):
        print(f"❌ No existe el archivo de URLs: {CSV_INPUT}"); return

    df_urls = pd.read_csv(CSV_INPUT)
    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
    
    urls_procesadas = set()
    if os.path.exists(CSV_OUTPUT) and os.path.getsize(CSV_OUTPUT) > 0:
        try:
            df_existente = pd.read_csv(CSV_OUTPUT)
            urls_procesadas = set(df_existente["URL_PRODUCTO"].tolist())
        except: pass

    s = requests.Session()

    with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not urls_procesadas:
            writer.writeheader()

        for i, row in df_urls.iterrows():
            url = row["URL_PRODUCTO"]
            if url in urls_procesadas: continue

            print(f"🔎 [{i+1}/{len(df_urls)}] {url}")
            soup = get_soup(s, url)
            
            if not soup: continue

            # --- EXTRACCIÓN Y LIMPIEZA DE SKU ---
            sku_final = "N/A"
            carousel_div = soup.select_one("div[id^='pdpCarousel-']")
            if carousel_div:
                sku_raw = carousel_div.get("id", "").replace("pdpCarousel-", "")
                # Limpieza: quitamos el prefijo MXYZ_ para dejar solo los números
                sku_final = sku_raw.replace("MXYZ_", "").strip()

            # --- RESTO DE DATOS ---
            nombre_elem = soup.select_one("h1.product-name")
            nombre = nombre_elem.get_text(strip=True) if nombre_elem else "N/A"

            p_oferta_el = soup.select_one("span.sales .value")
            p_actual_el = soup.select_one("span.list .value")
            
            precio_oferta = clean_price(p_oferta_el.get_text(strip=True)) if p_oferta_el else "0.00"
            precio_actual = clean_price(p_actual_el.get_text(strip=True)) if p_actual_el else "0.00"

            # Ajuste de precios (si uno es 0, usar el otro)
            if precio_oferta == "0.00": precio_oferta = precio_actual
            if precio_actual == "0.00": precio_actual = precio_oferta

            img_el = soup.select_one(".carousel-item.active img")
            url_imagen = img_el.get("src") if img_el else ""
            if url_imagen and url_imagen.startswith("/"):
                url_imagen = "https://www.yza.mx" + url_imagen

            writer.writerow({
                "SKU": sku_final,
                "URL_PRODUCTO": url,
                "Producto": nombre,
                "Precio_Actual": precio_actual,
                "Precio_Oferta": precio_oferta,
                "URL_IMAGEN": url_imagen,
                "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Tienda": TIENDA,
            })
            f.flush()
            print(f"   ✅ SKU Limpio: {sku_final} | ${precio_oferta}")
            
            time.sleep(1.2)

if __name__ == "__main__":
    main()