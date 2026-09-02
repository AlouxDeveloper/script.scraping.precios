import os
import csv
import time
import requests
import pandas as pd
import re
from datetime import datetime

# ========== Configuración ==========
EXCEL_CATEGORIAS = "./data/urls_categorias_alsuper.xlsx" 
COLUMNA_EXCEL = "URL_CATEGORIA" 
CSV_OUTPUT = "./salida/data/2026/09_septiembre/scraping_detalle_alsuper.csv"
TIENDA = "22"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://alsuper.com/",
}

CSV_FIELDS = ["SKU", "URL_PRODUCTO", "Producto", "Precio_Actual", "Precio_Oferta", "URL_IMAGEN", "Fecha_Hora_Captura", "Tienda"]

def main():
    if not os.path.exists(EXCEL_CATEGORIAS):
        print(f"❌ No se encontró el Excel: {EXCEL_CATEGORIAS}"); return

    df_cat = pd.read_excel(EXCEL_CATEGORIAS)
    lista_urls_api = df_cat[COLUMNA_EXCEL].dropna().tolist()

    os.makedirs(os.path.dirname(CSV_OUTPUT), exist_ok=True)
    skus_vistos = set()

    print(f"🚀 Iniciando scraping de Alsuper (Estructura Anidada)...")

    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for url_base in lista_urls_api:
            # Limpieza de parámetros de página previos
            url_limpia = re.sub(r'([?&])page=\d+', r'\1', url_base)
            url_limpia = re.sub(r'([?&])limit=\d+', r'\1', url_limpia).replace('&&', '&').replace('?&', '?').rstrip('&').rstrip('?')
            separador = "&" if "?" in url_limpia else "?"
            
            page = 1
            while True:
                api_url = f"{url_limpia}{separador}page={page}&limit=50"
                print(f"🔎 Consultando: {api_url}")
                
                try:
                    response = requests.get(api_url, headers=HEADERS, timeout=20)
                    if response.status_code != 200:
                        break
                    
                    json_res = response.json()
                    
                    # --- NUEVA LÓGICA DE NAVEGACIÓN JSON ---
                    # Accedemos a data -> data (que es una lista) -> items (lista de productos)
                    categorias_en_json = json_res.get("data", {}).get("data", [])
                    
                    if not categorias_en_json:
                        break

                    hay_productos_en_esta_pagina = False
                    
                    for cat_data in categorias_en_json:
                        items = cat_data.get("items", [])
                        if items:
                            hay_productos_en_esta_pagina = True
                        
                        for prod in items:
                            sku = str(prod.get("sku") or prod.get("id") or prod.get("objectID"))
                            
                            if sku not in skus_vistos:
                                # Precios
                                precio_f = float(prod.get("price", 0))
                                precio_r = float(prod.get("regular_price", 0))
                                
                                # Si el precio de oferta es 0 o no existe, usamos el regular
                                if precio_f == 0: precio_f = precio_r
                                if precio_r == 0: precio_r = precio_f

                                writer.writerow({
                                    "SKU": sku,
                                    "URL_PRODUCTO": prod.get("share_url") or f"https://alsuper.com/producto/{sku}",
                                    "Producto": prod.get("name"),
                                    "Precio_Actual": "{:.2f}".format(precio_r),
                                    "Precio_Oferta": "{:.2f}".format(precio_f),
                                    "URL_IMAGEN": prod.get("image_url"),
                                    "Fecha_Hora_Captura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "Tienda": TIENDA
                                })
                                skus_vistos.add(sku)
                    
                    if not hay_productos_en_esta_pagina:
                        print("   🏁 No se encontraron más items.")
                        break

                    f.flush()
                    print(f"   ✅ Página {page} procesada. Total: {len(skus_vistos)}")
                    
                    page += 1
                    time.sleep(0.5)

                except Exception as e:
                    print(f"   💥 Error: {e}")
                    break

    print(f"\n🎯 Proceso terminado. Total: {len(skus_vistos)} productos únicos.")

if __name__ == "__main__":
    main()