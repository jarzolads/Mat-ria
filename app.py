import copy
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from google import genai
from google.genai import types
from mp_api.client import MPRester


st.set_page_config(
    page_title="Matéria",
    page_icon="🔬",
    layout="wide",
)


# ============================================================
# CONFIGURACIÓN INICIAL
# ============================================================

MODELO_GEMINI = "gemini-flash-latest"

EJEMPLO = (
    "Busca óxidos de hierro con magnetización calculada "
    "por volumen mínima de 0.02 μB/Å³ y energía sobre la "
    "envolvente máxima de 0.05 eV/átomo."
)


def secreto(nombre, valor_default=""):
    try:
        return st.secrets.get(nombre, valor_default)
    except FileNotFoundError:
        return valor_default


def fecha_utc():
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# DEFINICIONES EDUCATIVAS
# ============================================================

DEFINICIONES = {
    "Magnetización por volumen": {
        "definicion": (
            "Es el momento magnético calculado por unidad de volumen "
            "del cristal."
        ),
        "importancia": (
            "Permite identificar materiales con comportamiento magnético "
            "calculado potencialmente interesante."
        ),
        "limitacion": (
            "No equivale al SAR y no predice directamente cuánto "
            "calentará una nanopartícula."
        ),
        "unidad": "μB/Å³",
    },
    "Energía sobre la envolvente": {
        "definicion": (
            "Es la distancia energética entre el material y la combinación "
            "de fases más estable calculada para su composición."
        ),
        "importancia": (
            "Un valor menor indica mayor estabilidad termodinámica calculada "
            "respecto a las fases de referencia."
        ),
        "limitacion": (
            "No garantiza que el material pueda sintetizarse fácilmente "
            "ni que sea estable bajo cualquier condición experimental."
        ),
        "unidad": "eV/átomo",
    },
    "Ordenamiento magnético": {
        "definicion": (
            "Describe la configuración calculada de los momentos magnéticos, "
            "por ejemplo ferromagnética o antiferromagnética."
        ),
        "importancia": (
            "Ayuda a describir el comportamiento magnético calculado "
            "del material."
        ),
        "limitacion": (
            "El resultado corresponde al cálculo del cristal y no demuestra "
            "el comportamiento de una nanopartícula real."
        ),
        "unidad": "clasificación",
    },
    "Densidad": {
        "definicion": (
            "Es la masa del material por unidad de volumen."
        ),
        "importancia": (
            "Ayuda a comparar materiales y estimar cantidades requeridas."
        ),
        "limitacion": (
            "No es una medida directa del desempeño en hipertermia."
        ),
        "unidad": "g/cm³",
    },
}


# ============================================================
# RECETA Y COSTOS EDUCATIVOS
# ============================================================

RECETA_FE3O4 = {
    "nombre": "Coprecipitación de magnetita como ejemplo didáctico",
    "evidencia": (
        "Plantilla educativa. Debe sustituirse por una receta bibliográfica "
        "verificada antes de realizar una síntesis."
    ),
    "pasos": [
        "Seleccionar precursores de hierro(II) y hierro(III).",
        "Preparar una disolución con concentración conocida.",
        "Agregar una base bajo agitación y pH controlado.",
        "Separar y lavar el precipitado.",
        "Secar el material obtenido.",
        "Caracterizar fase, tamaño, morfología y propiedades magnéticas.",
    ],
}

COSTOS_EJEMPLO = pd.DataFrame([
    {
        "Material": "Precursor de Fe(III)",
        "Cantidad_g": 0.80,
        "Precio_paquete_MXN": 850.00,
        "Paquete_g": 500.00,
    },
    {
        "Material": "Precursor de Fe(II)",
        "Cantidad_g": 0.40,
        "Precio_paquete_MXN": 1200.00,
        "Paquete_g": 500.00,
    },
    {
        "Material": "Base",
        "Cantidad_g": 0.60,
        "Precio_paquete_MXN": 300.00,
        "Paquete_g": 1000.00,
    },
    {
        "Material": "Agua desionizada",
        "Cantidad_g": 20.00,
        "Precio_paquete_MXN": 80.00,
        "Paquete_g": 1000.00,
    },
])


def calcular_costos(factor_escala=1.0):
    tabla = COSTOS_EJEMPLO.copy()

    tabla["Cantidad_escala_g"] = (
        tabla["Cantidad_g"] * factor_escala
    )

    tabla["Costo_MXN"] = (
        tabla["Cantidad_escala_g"]
        * tabla["Precio_paquete_MXN"]
        / tabla["Paquete_g"]
    )

    costo_precursores = tabla["Costo_MXN"].sum()

    energia = 25.00
    consumibles = 50.00

    total = costo_precursores + energia + consumibles

    resumen = {
        "Precursores": costo_precursores,
        "Energía": energia,
        "Consumibles": consumibles,
        "Total": total,
    }

    return tabla, resumen


# ============================================================
# MATERIALS PROJECT
# ============================================================


def descargar_materiales():
    api_key = secreto("MP_API_KEY")

    if not api_key:
        raise ValueError(
            "No existe MP_API_KEY en los secretos de Streamlit."
        )

    campos = [
        "material_id",
        "formula_pretty",
        "chemsys",
        "density",
        "energy_above_hull",
        "ordering",
        "total_magnetization_normalized_vol",
        "symmetry",
    ]

    with MPRester(
        api_key,
        use_document_model=False,
    ) as mpr:

        documentos = mpr.materials.summary.search(
            chemsys=["Fe-O"],
            deprecated=False,
            fields=campos,
        )

    filas = []

    for documento in documentos:

        ordenamiento = documento.get("ordering")

        if hasattr(ordenamiento, "value"):
            ordenamiento = ordenamiento.value

        simetria = documento.get("symmetry") or {}

        filas.append({
            "material_id": str(
                documento.get("material_id")
            ),
            "formula": documento.get(
                "formula_pretty"
            ),
            "sistema": documento.get(
                "chemsys"
            ),
            "densidad": documento.get(
                "density"
            ),
            "E_hull": documento.get(
                "energy_above_hull"
            ),
            "M_vol": documento.get(
                "total_magnetization_normalized_vol"
            ),
            "ordenamiento": ordenamiento,
            "grupo_espacial": simetria.get(
                "symbol"
            ),
        })

    datos = pd.DataFrame(filas)

    for columna in [
        "densidad",
        "E_hull",
        "M_vol",
    ]:
        datos[columna] = pd.to_numeric(
            datos[columna],
            errors="coerce",
        )

    return datos


# ============================================================
# BÚSQUEDA INVERSA
# ============================================================


def buscar_candidatos(
    datos,
    magnetizacion_minima=0.02,
    hull_maximo=0.05,
    densidad_maxima=None,
):
    resultado = datos.copy()

    razones = []
    estados = []
    distancias = []

    for _, fila in resultado.iterrows():

        motivos = []
        distancia = 0.0

        magnetizacion = fila["M_vol"]
        energia = fila["E_hull"]
        densidad = fila["densidad"]

        if pd.isna(magnetizacion):
            motivos.append(
                "No hay magnetización calculada"
            )
            estados.append("Sin datos suficientes")
            razones.append("; ".join(motivos))
            distancias.append(np.nan)
            continue

        if pd.isna(energia):
            motivos.append(
                "No hay energía sobre la envolvente"
            )
            estados.append("Sin datos suficientes")
            razones.append("; ".join(motivos))
            distancias.append(np.nan)
            continue

        if energia > hull_maximo:
            motivos.append(
                "Supera E_hull máximo"
            )

        if magnetizacion < magnetizacion_minima:
            motivos.append(
                "Magnetización inferior al objetivo"
            )
            distancia += (
                magnetizacion_minima - magnetizacion
            ) / magnetizacion_minima

        if (
            densidad_maxima is not None
            and not pd.isna(densidad)
            and densidad > densidad_maxima
        ):
            motivos.append(
                "Densidad superior al objetivo"
            )
            distancia += (
                densidad - densidad_maxima
            ) / densidad_maxima

        if energia <= hull_maximo and not motivos:
            estado = "Cumple objetivos"
        elif energia > hull_maximo:
            estado = "Excluido"
        else:
            estado = "Aproximado"

        estados.append(estado)
        razones.append("; ".join(motivos))
        distancias.append(distancia)

    resultado["estado"] = estados
    resultado["motivos"] = razones
    resultado["distancia"] = distancias

    orden = {
        "Cumple objetivos": 0,
        "Aproximado": 1,
        "Sin datos suficientes": 2,
        "Excluido": 3,
    }

    resultado["_orden"] = resultado["estado"].map(orden)

    resultado = resultado.sort_values(
        ["_orden", "distancia"],
        na_position="last",
    )

    return resultado.drop(
        columns="_orden"
    ).reset_index(drop=True)


# ============================================================
# AGENTE GEMINI
# ============================================================


DECLARACION_BUSQUEDA = types.FunctionDeclaration(
    name="buscar_materiales",
    description=(
        "Busca materiales de Fe-O que cumplan objetivos "
        "de magnetización, estabilidad y opcionalmente densidad."
    ),
    parameters={
        "type": "object",
        "properties": {
            "magnetizacion_minima": {
                "type": "number",
                "description": (
                    "Magnetización mínima en μB/Å³."
                ),
            },
            "hull_maximo": {
                "type": "number",
                "description": (
                    "Energía sobre la envolvente máxima "
                    "en eV/átomo."
                ),
            },
            "densidad_maxima": {
                "type": [
                    "number",
                    "null",
                ],
                "description": (
                    "Densidad máxima en g/cm³, "
                    "o null si no se solicita."
                ),
            },
        },
        "required": [
            "magnetizacion_minima",
            "hull_maximo",
            "densidad_maxima",
        ],
    },
)


INSTRUCCIONES_GEMINI = """
Eres Matéria, un agente educativo de diseño inverso de materiales.

El usuario expresa propiedades deseadas. Tú debes convertir su solicitud
en argumentos para la herramienta buscar_materiales.

Reglas:

- Trabaja únicamente con registros Fe-O que ya fueron descargados.
- No inventes materiales ni propiedades.
- Si el usuario pide más magnetización, aumenta magnetizacion_minima.
- Si pide mayor estabilidad o menor energía, reduce hull_maximo.
- Si pide baja densidad, utiliza densidad_maxima.
- Si el usuario no solicita densidad, utiliza null.
- Las unidades son μB/Å³, eV/átomo y g/cm³.
- No afirmes que el material tendrá alto SAR.
- No afirmes que una propiedad calculada demuestra biocompatibilidad.
- Explica en español qué pidió el usuario y cuántos candidatos cumplen.
- Menciona como máximo tres material_id.
- No describas todos los registros de la tabla.
"""


def ejecutar_agente(
    pregunta,
    datos,
):
    api_key = secreto("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "No existe GEMINI_API_KEY en los secretos."
        )

    cliente = genai.Client(
        api_key=api_key
    )

    configuracion = types.GenerateContentConfig(
        system_instruction=INSTRUCCIONES_GEMINI,
        tools=[
            types.Tool(
                function_declarations=[
                    DECLARACION_BUSQUEDA
                ]
            )
        ],
        automatic_function_calling=(
            types.AutomaticFunctionCallingConfig(
                disable=True
            )
        ),
    )

    respuesta = cliente.models.generate_content(
        model=secreto(
            "GEMINI_MODEL",
            MODELO_GEMINI,
        ),
        contents=pregunta,
        config=configuracion,
    )

    llamadas = []

    if respuesta.candidates:
        contenido = respuesta.candidates[0].content

        if contenido and contenido.parts:
            llamadas = [
                parte.function_call
                for parte in contenido.parts
                if parte.function_call is not None
            ]

    if not llamadas:
        return (
            respuesta.text
            or "Gemini no produjo una solicitud estructurada.",
            None,
            None,
        )

    llamada = llamadas[0]
    argumentos = dict(llamada.args)

    resultado = buscar_candidatos(
        datos,
        magnetizacion_minima=float(
            argumentos["magnetizacion_minima"]
        ),
        hull_maximo=float(
            argumentos["hull_maximo"]
        ),
        densidad_maxima=(
            None
            if argumentos["densidad_maxima"] is None
            else float(
                argumentos["densidad_maxima"]
            )
        ),
    )

    resumen = {
        "total_materiales": len(resultado),
        "cumplen": int(
            (
                resultado["estado"]
                == "Cumple objetivos"
            ).sum()
        ),
        "aproximados": int(
            (
                resultado["estado"]
                == "Aproximado"
            ).sum()
        ),
        "candidatos": json.loads(
            resultado.head(5).to_json(
                orient="records",
                double_precision=8,
            )
        ),
    }

    respuesta_funcion = types.Part(
        function_response=types.FunctionResponse(
            name="buscar_materiales",
            response=resumen,
        )
    )

    respuesta_final = cliente.models.generate_content(
        model=secreto(
            "GEMINI_MODEL",
            MODELO_GEMINI,
        ),
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=pregunta
                    )
                ],
            ),
            respuesta.candidates[0].content,
            types.Content(
                role="user",
                parts=[respuesta_funcion],
            ),
        ],
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCCIONES_GEMINI,
        ),
    )

    return (
        respuesta_final.text
        or "La búsqueda fue ejecutada.",
        argumentos,
        resultado,
    )


# ============================================================
# ESTADO DE STREAMLIT
# ============================================================


if "datos" not in st.session_state:
    st.session_state.datos = None

if "resultado" not in st.session_state:
    st.session_state.resultado = None

if "historial" not in st.session_state:
    st.session_state.historial = []


# ============================================================
# INTERFAZ
# ============================================================


st.title("🔬 Matéria")

st.subheader(
    "Demostración de diseño inverso de materiales"
)

st.write(
    "En lugar de preguntar qué propiedades tiene un material, "
    "comenzamos indicando qué propiedades deseamos."
)

st.info(
    "Ejemplo: «Busca óxidos de hierro con magnetización "
    "mínima de 0.02 μB/Å³ y E_hull máximo de 0.05 eV/átomo»."
)


col1, col2 = st.columns(2)

if col1.button(
    "Cargar datos de Materials Project",
    use_container_width=True,
):

    try:

        with st.spinner(
            "Descargando registros Fe-O..."
        ):
            st.session_state.datos = (
                descargar_materiales()
            )

        st.success(
            f"Se descargaron "
            f"{len(st.session_state.datos)} registros."
        )

    except Exception as error:
        st.error(
            f"No se pudieron descargar los datos: "
            f"{type(error).__name__}: {error}"
        )


if col2.button(
    "Probar diseño inverso",
    use_container_width=True,
):

    if st.session_state.datos is None:

        st.warning(
            "Primero carga los datos de Materials Project."
        )

    else:

        try:

            with st.spinner(
                "Gemini interpreta la solicitud..."
            ):

                texto, criterios, resultado = (
                    ejecutar_agente(
                        EJEMPLO,
                        st.session_state.datos,
                    )
                )

            st.session_state.historial.append(
                {
                    "usuario": EJEMPLO,
                    "agente": texto,
                }
            )

            st.session_state.resultado = resultado

        except Exception as error:
            st.error(
                f"No se pudo ejecutar el agente: "
                f"{type(error).__name__}: {error}"
            )


st.divider()

pregunta = st.chat_input(
    "Escribe las propiedades que deseas"
)

if pregunta:

    if st.session_state.datos is None:

        st.warning(
            "Primero carga los datos de Materials Project."
        )

    else:

        try:

            with st.spinner(
                "Gemini está interpretando tu solicitud..."
            ):

                texto, criterios, resultado = (
                    ejecutar_agente(
                        pregunta,
                        st.session_state.datos,
                    )
                )

            st.session_state.historial.append(
                {
                    "usuario": pregunta,
                    "agente": texto,
                }
            )

            st.session_state.resultado = resultado

        except Exception as error:
            st.error(
                f"No se pudo ejecutar la búsqueda: "
                f"{type(error).__name__}: {error}"
            )


if st.session_state.historial:

    st.subheader("Conversación")

    for intercambio in st.session_state.historial:

        with st.chat_message("user"):
            st.write(
                intercambio["usuario"]
            )

        with st.chat_message("assistant"):
            st.write(
                intercambio["agente"]
            )


if st.session_state.resultado is not None:

    resultado = st.session_state.resultado

    st.subheader("Candidatos encontrados")

    completos = resultado[
        resultado["estado"]
        == "Cumple objetivos"
    ]

    aproximados = resultado[
        resultado["estado"]
        == "Aproximado"
    ]

    c1, c2 = st.columns(2)

    c1.metric(
        "Cumplen objetivos",
        len(completos),
    )

    c2.metric(
        "Candidatos aproximados",
        len(aproximados),
    )

    st.dataframe(
        resultado[
            [
                "formula",
                "material_id",
                "M_vol",
                "E_hull",
                "densidad",
                "ordenamiento",
                "estado",
                "motivos",
            ]
        ].head(10),
        hide_index=True,
        use_container_width=True,
    )

    st.caption(
        "La tabla muestra una búsqueda entre materiales "
        "registrados. No representa una predicción directa "
        "de SAR o eficacia biomédica."
    )

    st.subheader(
        "Visualización de candidatos"
    )

    graficables = resultado.dropna(
        subset=["M_vol", "E_hull"]
    )

    if not graficables.empty:

        figura = px.scatter(
            graficables,
            x="E_hull",
            y="M_vol",
            color="estado",
            hover_name="formula",
            hover_data=[
                "material_id",
                "densidad",
                "ordenamiento",
            ],
            labels={
                "E_hull": "Energía sobre la envolvente (eV/átomo)",
                "M_vol": "Magnetización (μB/Å³)",
            },
        )

        st.plotly_chart(
            figura,
            use_container_width=True,
        )


# ============================================================
# GLOSARIO
# ============================================================


st.divider()

st.subheader(
    "Conceptos científicos"
)

for nombre, informacion in DEFINICIONES.items():

    with st.expander(
        f"{nombre} ({informacion['unidad']})"
    ):

        st.write(
            informacion["definicion"]
        )

        st.markdown(
            f"**Por qué importa:** "
            f"{informacion['importancia']}"
        )

        st.markdown(
            f"**Limitación:** "
            f"{informacion['limitacion']}"
        )


# ============================================================
# SÍNTESIS Y COSTOS
# ============================================================


st.divider()

st.subheader(
    "Estrategia de síntesis y costo preliminar"
)

st.write(
    "Esta sección es educativa. Los precios y cantidades "
    "deben sustituirse por datos verificados."
)

st.markdown(
    "**Material de referencia:** Fe₃O₄"
)

st.markdown(
    "**Estrategia:** "
    f"{RECETA_FE3O4['nombre']}"
)

st.caption(
    RECETA_FE3O4["evidencia"]
)

for paso in RECETA_FE3O4["pasos"]:
    st.write(f"• {paso}")

tabla_costos, resumen_costos = calcular_costos()

st.dataframe(
    tabla_costos,
    hide_index=True,
    use_container_width=True,
)

a, b, c = st.columns(3)

a.metric(
    "Precursores",
    f"${resumen_costos['Precursores']:.2f} MXN",
)

b.metric(
    "Energía",
    f"${resumen_costos['Energía']:.2f} MXN",
)

c.metric(
    "Total preliminar",
    f"${resumen_costos['Total']:.2f} MXN",
)

st.warning(
    "Los precios son ilustrativos y no constituyen una cotización. "
    "La estrategia no sustituye un protocolo experimental validado."
)


# ============================================================
# REGISTRO
# ============================================================


with st.expander(
    "Ver criterios y registro"
):

    if st.session_state.resultado is not None:

        st.write(
            "Criterios interpretados por Gemini:"
        )

        st.json(
            st.session_state.historial[-1]
        )

        st.write(
            "Los datos fueron consultados desde Materials Project "
            "y procesados con Python."
        )
