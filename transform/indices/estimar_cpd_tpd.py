"""Estima el nivel de precios por cadena (CPD) y el índice temporal (TPD).

Lee ``precios_gold.mart_precio_cadena_mes`` (portafolio del cliente, sin
atípicos) y escribe con ``WRITE_TRUNCATE`` sus dos tablas en
``precios_gold``, las únicas que toca:

- ``mart_cpd_cadena_mes`` (M5): por mes, OLS de ``ln p ~ producto +
  cadena`` con restricción de suma cero sobre las cadenas. El nivel de cada
  cadena es ``e^β − 1`` contra la cadena promedio, con IC95%.
- ``mart_tpd_indice_mes`` (M6): OLS de ``ln p ~ artículo + mes`` sobre todo
  el panel, artículo = (presentación, cadena). Índice ``100·e^δ`` con base
  en la var ``mes_base_tpd`` de ``dbt_project.yml``, y su variación contra
  el mes calendario anterior (``variacion_pct``, NULL si ese mes falta).

Vive fuera de dbt porque BigQuery ML no expone la covarianza completa de
los coeficientes, y sin ella no hay error estándar para la cadena omitida
ni intervalo "contra el mercado". Solo se estima el portafolio completo:
los filtros de Looker no recalculan estos modelos.

Corre después del ``dbt build`` del refresco mensual, desde la raíz del
repo:

    uv run --project transform transform/indices/estimar_cpd_tpd.py
    uv run --project transform transform/indices/estimar_cpd_tpd.py --probar

``--probar`` no toca BigQuery: verifica los dos estimadores con datos
simulados de efectos conocidos.
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
import yaml
from google.cloud import bigquery

PROJECT_ID = "scenic-firefly-473823-f7"
LOCATION = "US"
DATASET = "precios_gold"
TABLA_CPD = "mart_cpd_cadena_mes"
TABLA_TPD = "mart_tpd_indice_mes"
DBT_PROJECT = Path("transform/dbt/precios/dbt_project.yml")

# Cuantil 0.975 de la normal: el PRD define los intervalos con 1.96·se.
Z95 = 1.959964
# Un producto en una sola cadena no aporta nada al efecto de cadena y, si
# es el único vínculo de una cadena, desconecta el diseño.
MIN_CADENAS_POR_PRODUCTO = 2
# Debajo de esto la cadena se marca "Estimación inestable" (PRD M5).
MIN_PRODUCTOS_ESTABLE = 30
MODO_PROBAR = "--probar"

CONSULTA = f"""
    select
        ndf_id,
        tienda_key,
        cadena,
        mes,
        cast(precio as float64) as precio
    from `{PROJECT_ID}.{DATASET}.mart_precio_cadena_mes`
    where es_cliente and not es_atipico
"""


def estimar_cpd_mes(precios: pd.DataFrame) -> pd.DataFrame:
    """Estima el CPD de un mes y devuelve una fila por cadena.

    Con codificación de suma cero (``C(tienda_key, Sum)``) statsmodels
    estima J−1 efectos y la cadena omitida vale menos su suma. Los J efectos
    y sus errores estándar salen de un solo contraste, ``L·b``, que usa la
    covarianza completa de los coeficientes; la fila de la cadena omitida es
    ``−1`` en todas las demás.
    """
    cadenas_por_producto = precios.groupby("ndf_id")["tienda_key"].transform(
        "nunique"
    )
    precios = precios[cadenas_por_producto >= MIN_CADENAS_POR_PRODUCTO].copy()
    precios["ln_precio"] = np.log(precios["precio"])

    modelo = smf.ols(
        "ln_precio ~ C(ndf_id) + C(tienda_key, Sum)", data=precios
    ).fit()
    # Rango incompleto = diseño desconectado (grupos de cadenas sin
    # productos en común): los efectos no serían comparables entre sí.
    assert modelo.model.rank == modelo.model.exog.shape[1], (
        "Diseño CPD desconectado"
    )

    cadenas = sorted(precios["tienda_key"].unique())
    columnas = [
        modelo.params.index.get_loc(nombre)
        for nombre in modelo.params.index
        if nombre.startswith("C(tienda_key, Sum)")
    ]
    contrastes = np.zeros((len(cadenas), len(modelo.params)))
    for fila, columna in enumerate(columnas):
        contrastes[fila, columna] = 1.0
    contrastes[-1, columnas] = -1.0
    resultado = modelo.t_test(contrastes)
    beta = np.asarray(resultado.effect).ravel()
    error = np.asarray(resultado.sd).ravel()

    productos = precios.groupby("tienda_key")["ndf_id"].nunique()
    nombres = precios.groupby("tienda_key")["cadena"].first()
    return pd.DataFrame(
        {
            "tienda_key": cadenas,
            "cadena": nombres.loc[cadenas].to_numpy(),
            "beta": beta,
            "error_estandar": error,
            "nivel_pct": np.expm1(beta),
            "ic95_inf": np.expm1(beta - Z95 * error),
            "ic95_sup": np.expm1(beta + Z95 * error),
            "productos_n": productos.loc[cadenas].to_numpy(),
            "precios_n": len(precios),
        }
    ).assign(
        estimacion_inestable=lambda d: d["productos_n"] < MIN_PRODUCTOS_ESTABLE
    )


def estimar_cpd(precios: pd.DataFrame) -> pd.DataFrame:
    """Estima el CPD de cada mes por separado y los apila."""
    return pd.concat(
        [
            estimar_cpd_mes(del_mes).assign(mes=mes)
            for mes, del_mes in precios.groupby("mes")
        ],
        ignore_index=True,
    )


def estimar_tpd(precios: pd.DataFrame, mes_base: date) -> pd.DataFrame:
    """Estima el índice TPD de todo el panel con base en ``mes_base``.

    Los ~2,400 efectos de artículo se absorben por Frisch-Waugh-Lovell: se
    resta a ``ln p`` y a cada dummy de mes su promedio dentro del artículo y
    se regresa sin constante. Los δ son idénticos a los de la regresión con
    dummies, pero la varianza residual de OLS divide entre ``n − k`` y los
    efectos absorbidos consumen ``a`` grados de libertad más; la covarianza
    se escala por ``(n − k) / (n − a − k)``.
    """
    precios = precios.copy()
    precios["ln_precio"] = np.log(precios["precio"])
    articulo = precios["ndf_id"] + "|" + precios["tienda_key"].astype(str)
    meses = sorted(precios["mes"].unique())
    assert mes_base in meses, f"El mes base {mes_base} no está en el panel"
    otros = [mes for mes in meses if mes != mes_base]

    dummies = pd.DataFrame(
        {str(mes): (precios["mes"] == mes).astype(float) for mes in otros}
    )
    y = precios["ln_precio"] - precios.groupby(articulo)[
        "ln_precio"
    ].transform("mean")
    x = dummies - dummies.groupby(articulo).transform("mean")
    modelo = sm.OLS(y.to_numpy(), x.to_numpy()).fit()

    n, k, a = len(precios), len(otros), articulo.nunique()
    covarianza = modelo.cov_params() * (n - k) / (n - a - k)
    delta = dict(zip(otros, modelo.params))
    error = dict(zip(otros, np.sqrt(np.diag(covarianza))))
    delta[mes_base], error[mes_base] = 0.0, 0.0

    # Un artículo visto en un solo mes no informa ningún δ: su efecto
    # absorbe todo su precio. Se reporta aparte de los precios del mes.
    meses_por_articulo = precios.groupby(articulo)["mes"].transform("nunique")
    conteos = (
        precios.assign(informativo=meses_por_articulo > 1)
        .groupby("mes")
        .agg(
            precios_n=("precio", "size"),
            articulos_n=("informativo", "sum"),
        )
    )
    indice = pd.DataFrame({"mes": meses})
    indice["delta"] = indice["mes"].map(delta)
    indice["error_estandar"] = indice["mes"].map(error)
    indice["indice"] = 100 * np.exp(indice["delta"])
    indice["ic95_inf"] = 100 * np.exp(
        indice["delta"] - Z95 * indice["error_estandar"]
    )
    indice["ic95_sup"] = 100 * np.exp(
        indice["delta"] + Z95 * indice["error_estandar"]
    )
    indice["es_base"] = indice["mes"] == mes_base
    # Solo contra el mes calendario anterior: si el panel tiene un hueco,
    # comparar contra el último mes publicado mezclaría varios meses.
    por_mes = indice.set_index("mes")["indice"]
    anterior = indice["mes"].map(
        lambda mes: por_mes.get(
            date(mes.year - (mes.month == 1), (mes.month - 2) % 12 + 1, 1)
        )
    )
    indice["variacion_pct"] = indice["indice"] / anterior - 1
    return indice.join(conteos, on="mes")


def validar(cpd: pd.DataFrame, tpd: pd.DataFrame) -> None:
    """Revisa las invariantes antes de escribir; aborta si alguna falla."""
    assert not cpd.isna().any().any(), "CPD con valores nulos"
    # variacion_pct es NULL en el primer mes y tras un hueco del panel.
    assert not tpd.drop(columns="variacion_pct").isna().any().any(), (
        "TPD con valores nulos"
    )
    assert (cpd["ic95_inf"] <= cpd["nivel_pct"]).all(), "IC del CPD desordenado"
    assert (cpd["nivel_pct"] <= cpd["ic95_sup"]).all(), "IC del CPD desordenado"
    suma_beta = cpd.groupby("mes")["beta"].sum().abs().max()
    assert suma_beta < 1e-9, f"Los β no suman cero ({suma_beta})"
    assert (tpd["ic95_inf"] <= tpd["indice"]).all(), "IC del TPD desordenado"
    assert (tpd["indice"] <= tpd["ic95_sup"]).all(), "IC del TPD desordenado"
    base = tpd.loc[tpd["es_base"], "indice"]
    assert len(base) == 1 and np.isclose(base.iloc[0], 100), "Base ≠ 100"


def leer_mes_base() -> date:
    """Lee la var ``mes_base_tpd`` de ``dbt_project.yml``."""
    with DBT_PROJECT.open(encoding="utf-8") as archivo:
        variables = yaml.safe_load(archivo)["vars"]
    return date.fromisoformat(variables["mes_base_tpd"])


def escribir(
    cliente: bigquery.Client, datos: pd.DataFrame, tabla: str
) -> None:
    """Reemplaza la tabla completa: cada corrida re-estima todo el panel."""
    destino = f"{PROJECT_ID}.{DATASET}.{tabla}"
    configuracion = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    cliente.load_table_from_dataframe(
        datos, destino, job_config=configuracion
    ).result()
    print(f"{destino}: {len(datos)} filas")


def probar() -> None:
    """Recupera efectos conocidos de un panel simulado con celdas faltantes."""
    generador = np.random.default_rng(5)
    efecto_cadena = np.array([0.10, -0.10, 0.05, -0.05, 0.02, -0.02])
    meses = [date(2026, m, 1) for m in (4, 5, 6, 7)]
    efecto_mes = {meses[0]: -0.03, meses[1]: -0.01, meses[2]: 0.0,
                  meses[3]: 0.04}
    filas = []
    for producto in range(40):
        nivel = generador.normal(4, 1)
        for cadena, beta in enumerate(efecto_cadena):
            for mes in meses:
                # Un 20% de celdas vacías: el diseño real nunca es completo.
                if generador.random() < 0.2:
                    continue
                ln_precio = (nivel + beta + efecto_mes[mes]
                             + generador.normal(0, 0.01))
                filas.append((str(producto), cadena, f"C{cadena}", mes,
                              np.exp(ln_precio)))
    precios = pd.DataFrame(
        filas, columns=["ndf_id", "tienda_key", "cadena", "mes", "precio"]
    )

    cpd = estimar_cpd(precios)
    tpd = estimar_tpd(precios, meses[2])
    validar(cpd, tpd)
    # El CPD de cada mes absorbe el efecto del mes en los α: solo deben
    # quedar los β de cadena.
    for _, del_mes in cpd.groupby("mes"):
        assert np.allclose(del_mes["beta"], efecto_cadena, atol=0.01)
    esperado = np.array([efecto_mes[mes] for mes in meses])
    assert np.allclose(np.log(tpd["indice"] / 100), esperado, atol=0.01)
    assert np.isnan(tpd["variacion_pct"].iloc[0])
    assert np.allclose(
        tpd["variacion_pct"].iloc[1:],
        np.exp(np.diff(esperado)) - 1,
        atol=0.01,
    )
    print("Verificación con datos simulados: OK")


def main() -> None:
    """Lee el panel, estima, valida y escribe las dos tablas."""
    if MODO_PROBAR in sys.argv:
        probar()
        return

    cliente = bigquery.Client(project=PROJECT_ID, location=LOCATION)
    precios = cliente.query(CONSULTA).to_dataframe()
    # DATE llega como `dbdate` de db-dtypes; como `date` de Python se agrupa
    # y se une igual que en `probar()`, y pyarrow lo vuelve a escribir DATE.
    precios["mes"] = pd.to_datetime(precios["mes"]).dt.date
    # Los tipos nullable de BigQuery (`Int64`, `string`) no los entiende
    # patsy, que arma las dummies de la fórmula del CPD.
    precios = precios.astype(
        {"tienda_key": "int64", "ndf_id": object, "cadena": object}
    )
    cpd = estimar_cpd(precios)
    tpd = estimar_tpd(precios, leer_mes_base())
    validar(cpd, tpd)
    escribir(cliente, cpd, TABLA_CPD)
    escribir(cliente, tpd, TABLA_TPD)


if __name__ == "__main__":
    main()
