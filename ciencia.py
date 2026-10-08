import hashlib
import json
from datetime import datetime, timezone
from importlib.metadata import version
from typing import Literal

import numpy as np
import pandas as pd
from mp_api.client import MPRester
from pydantic import BaseModel, ConfigDict, Field
from pymatgen.core import Composition


# Sistemas disponibles en esta primera versión.
SISTEMAS = ["Al-O", "Mg-O", "Al-Mg-O"]

# Valores ilustrativos, modificables desde la interfaz.
CRITERIOS_INICIALES = {
    "sistemas": SISTEMAS.copy(),
    "densidad_max": 6.0,
    "corte_min": 0.0,
    "hull_max": 0.05,
}


class Criterios(BaseModel):
    """Comprueba los argumentos antes de ejecutar el análisis."""

    model_config = ConfigDict(extra="forbid")

    sistemas: list[
        Literal["Al-O", "Mg-O", "Al-Mg-O"]
    ] = Field(min_length=1)

    densidad_max: float = Field(
        gt=0,
        allow_inf_nan=False,
    )

    corte_min: float = Field(
        ge=0,
        allow_inf_nan=False,
    )

    hull_max: float = Field(
        ge=0,
        allow_inf_nan=False,
    )


def descargar_materiales(api_key):
    """Consulta Materials Project y conserva los datos incompletos."""

    campos = [
        "material_id",
        "formula_pretty",
        "chemsys",
        "density",
        "energy_above_hull",
        "shear_modulus",
        "bulk_modulus",
        "symmetry",
    ]

    with MPRester(
        api_key,
        use_document_model=False,
    ) as mpr:

        documentos = mpr.materials.summary.search(
            chemsys=SISTEMAS,
            deprecated=False,
            fields=campos,
        )

    if not documentos:
        raise ValueError(
            "Materials Project no devolvió registros."
        )

    filas = []

    for documento in documentos:
        modulo_corte = documento.get("shear_modulus") or {}
        modulo_volumen = documento.get("bulk_modulus") or {}
        simetria = documento.get("symmetry") or {}

        filas.append({
            "material_id": str(documento["material_id"]),
            "formula": documento["formula_pretty"],
            "sistema": documento["chemsys"],
            "densidad": documento.get("density"),
            "G_VRH": modulo_corte.get("vrh"),
            "K_VRH": modulo_volumen.get("vrh"),
            "E_hull": documento.get("energy_above_hull"),
            "grupo_espacial": simetria.get("symbol"),
        })

    datos = (
        pd.DataFrame(filas)
        .drop_duplicates("material_id")
        .reset_index(drop=True)
    )

    columnas_numericas = [
        "densidad",
        "G_VRH",
        "K_VRH",
        "E_hull",
    ]

    for columna in columnas_numericas:
        datos[columna] = pd.to_numeric(
            datos[columna],
            errors="coerce",
        )

    tabla_json = datos.sort_values(
        "material_id"
    ).to_json(
        orient="records",
        double_precision=15,
        force_ascii=False,
    )

    metadata = {
        "fuente": "Materials Project / materials.summary",
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "sistemas_consultados": SISTEMAS,
        "campos_consultados": campos,
        "deprecated": False,
        "sha256_tabla": hashlib.sha256(
            tabla_json.encode("utf-8")
        ).hexdigest(),
        "unidades": {
            "densidad": "g/cm3",
            "G_VRH": "GPa",
            "K_VRH": "GPa",
            "E_hull": "eV/atom",
        },
        "versiones": {
            paquete: version(paquete)
            for paquete in [
                "mp-api",
                "pymatgen",
                "pandas",
                "numpy",
            ]
        },
        "definicion_oxido": (
            "Composición nominal compatible con "
            "Al(+3), Mg(+2) y O(-2). "
            "No demuestra estados de oxidación reales."
        ),
    }

    return datos, metadata


def es_oxido_nominal(formula):
    """Aplica una regla composicional explícita."""

    composicion = Composition(formula).get_el_amt_dict()

    elementos_permitidos = {"Al", "Mg", "O"}

    if not set(composicion).issubset(elementos_permitidos):
        return False

    oxigeno = composicion.get("O", 0)

    carga_positiva = (
        3 * composicion.get("Al", 0)
        + 2 * composicion.get("Mg", 0)
    )

    return bool(
        oxigeno > 0
        and np.isclose(carga_positiva, 2 * oxigeno)
    )


def calcular_pareto(datos):
    """
    Objetivos:
    - Minimizar densidad.
    - Maximizar G_VRH.

    Un punto queda dominado cuando existe otro igual o mejor
    en ambos objetivos y estrictamente mejor en al menos uno.
    """

    densidad = datos["densidad"].to_numpy()
    rigidez = datos["G_VRH"].to_numpy()

    no_dominados = np.ones(
        len(datos),
        dtype=bool,
    )

    for i in range(len(datos)):
        igual_o_mejor = (
            (densidad <= densidad[i])
            & (rigidez >= rigidez[i])
        )

        estrictamente_mejor = (
            (densidad < densidad[i])
            | (rigidez > rigidez[i])
        )

        existe_dominante = np.any(
            igual_o_mejor & estrictamente_mejor
        )

        no_dominados[i] = not existe_dominante

    return no_dominados


def analizar_materiales(datos, criterios):
    """Aplica filtros y conserva las razones de descarte."""

    criterios = Criterios.model_validate(criterios)

    resultado = datos.copy()

    def obtener_motivos(fila):
        razones = []

        if fila["sistema"] not in criterios.sistemas:
            razones.append(
                "Sistema fuera de la selección"
            )

        try:
            oxido_valido = es_oxido_nominal(
                fila["formula"]
            )
        except (ValueError, TypeError):
            oxido_valido = False

        if not oxido_valido:
            razones.append(
                "Fuera de la definición nominal de óxido"
            )

        limites = [
            (
                "densidad",
                criterios.densidad_max,
                "max",
            ),
            (
                "G_VRH",
                criterios.corte_min,
                "min",
            ),
            (
                "E_hull",
                criterios.hull_max,
                "max",
            ),
        ]

        for columna, limite, tipo in limites:
            valor = fila[columna]

            if pd.isna(valor) or not np.isfinite(valor):
                razones.append(
                    f"{columna}: dato ausente o no finito"
                )
                continue

            if columna in ["densidad", "G_VRH"] and valor <= 0:
                razones.append(
                    f"{columna}: valor no positivo"
                )

            elif columna == "E_hull" and valor < 0:
                razones.append(
                    "E_hull: valor negativo; revisar"
                )

            elif tipo == "max" and valor > limite:
                razones.append(
                    f"{columna}: supera el máximo"
                )

            elif tipo == "min" and valor < limite:
                razones.append(
                    f"{columna}: inferior al mínimo"
                )

        return "; ".join(razones)

    resultado["motivo_descarte"] = resultado.apply(
        obtener_motivos,
        axis=1,
    )

    resultado["aceptado"] = (
        resultado["motivo_descarte"].eq("")
    )

    resultado["pareto"] = False

    seleccion = resultado.loc[
        resultado["aceptado"]
    ]

    resultado.loc[
        seleccion.index,
        "pareto",
    ] = calcular_pareto(seleccion)

    return resultado


def registros_json(datos):
    """Convierte una tabla a registros JSON, con null para NaN."""

    return json.loads(
        datos.to_json(
            orient="records",
            double_precision=15,
            force_ascii=False,
        )
    )
