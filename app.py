import copy
import json
from datetime import datetime, timezone

import plotly.express as px
import streamlit as st

from agente import conversar
from ciencia import (
    CRITERIOS_INICIALES,
    SISTEMAS,
    analizar_materiales,
    descargar_materiales,
    registros_json,
)


st.set_page_config(
    page_title="Matéria",
    page_icon="🔬",
    layout="wide",
)


modo = st.sidebar.radio(
    "Modo de trabajo",
    ["Diseño inverso (demo)", "Explorar óxidos"],
)

if modo == "Diseño inverso (demo)":
    from interfaz_inversa import mostrar_inverso

    mostrar_inverso()
    st.stop()


def secreto(nombre, predeterminado=""):
    """Lee los secretos configurados en Streamlit."""

    try:
        return st.secrets.get(
            nombre,
            predeterminado,
        )
    except FileNotFoundError:
        return predeterminado


def fecha_actual():
    return datetime.now(
        timezone.utc
    ).isoformat()


def mensaje_error(error, *claves):
    """Evita mostrar las claves si aparecen en una excepción."""

    texto = str(error)

    for clave in claves:
        if clave:
            texto = texto.replace(
                str(clave),
                "[CLAVE OCULTA]",
            )

    return f"{type(error).__name__}: {texto}"


# Inicializar el estado de la sesión.
if "criterios" not in st.session_state:
    st.session_state.criterios = copy.deepcopy(
        CRITERIOS_INICIALES
    )

if "mensajes" not in st.session_state:
    st.session_state.mensajes = []

if "registros" not in st.session_state:
    st.session_state.registros = []

if "revision_formulario" not in st.session_state:
    st.session_state.revision_formulario = 0


st.title("🔬 Matéria")

st.caption(
    "Agente con Gemini para el cribado multicriterio de óxidos."
)

st.write(
    "Explora el compromiso entre baja densidad y alto módulo "
    "de corte, sujeto a un límite de energía sobre la "
    "envolvente convexa."
)


# ---------------------------------------------------------
# PANEL LATERAL
# ---------------------------------------------------------
with st.sidebar:
    st.header("1. Cargar datos")

    st.caption(
        "Sistemas disponibles: Al–O, Mg–O y Al–Mg–O."
    )

    cargar = st.button(
        "Consultar Materials Project",
        use_container_width=True,
    )

    if cargar:
        clave_mp = secreto("MP_API_KEY")

        if not clave_mp:
            st.error(
                "Falta configurar MP_API_KEY "
                "en los secretos de Streamlit."
            )
        else:
            try:
                with st.spinner(
                    "Descargando y procesando materiales..."
                ):
                    datos, metadata = descargar_materiales(
                        clave_mp
                    )

                    resultado = analizar_materiales(
                        datos,
                        st.session_state.criterios,
                    )

                st.session_state.datos = datos
                st.session_state.metadata = metadata
                st.session_state.resultado = resultado

                # Una nueva descarga inicia un expediente nuevo.
                st.session_state.mensajes = []
                st.session_state.registros = [{
                    "origen": "carga_datos",
                    "fecha_utc": fecha_actual(),
                    "criterios": copy.deepcopy(
                        st.session_state.criterios
                    ),
                    "sha256_tabla": metadata["sha256_tabla"],
                }]

                st.success(
                    f"Se descargaron {len(datos)} registros."
                )

            except Exception as error:
                st.error(
                    "No se pudo completar la consulta."
                )
                st.code(
                    mensaje_error(
                        error,
                        clave_mp,
                    ),
                    language="text",
                )

    st.divider()
    st.header("2. Definir criterios")

    criterios = st.session_state.criterios
    revision = st.session_state.revision_formulario

    # La revisión permite actualizar los controles
    # cuando el chat cambia los criterios.
    with st.form(
        key=f"filtros_{revision}"
    ):
        sistemas = st.multiselect(
            "Sistemas químicos",
            options=SISTEMAS,
            default=criterios["sistemas"],
            key=f"sistemas_{revision}",
        )

        densidad = st.number_input(
            "Densidad máxima (g/cm³)",
            min_value=0.0,
            value=float(
                criterios["densidad_max"]
            ),
            step=0.1,
            format="%.4f",
            key=f"densidad_{revision}",
        )

        corte = st.number_input(
            "Módulo de corte mínimo (GPa)",
            min_value=0.0,
            value=float(
                criterios["corte_min"]
            ),
            step=10.0,
            format="%.4f",
            key=f"corte_{revision}",
        )

        hull = st.number_input(
            "Energía sobre la envolvente máxima (eV/átomo)",
            min_value=0.0,
            value=float(
                criterios["hull_max"]
            ),
            step=0.01,
            format="%.4f",
            key=f"hull_{revision}",
        )

        aplicar = st.form_submit_button(
            "Aplicar filtros",
            use_container_width=True,
        )

    if aplicar:
        if not sistemas:
            st.error(
                "Selecciona al menos un sistema."
            )

        elif densidad <= 0:
            st.error(
                "La densidad máxima debe ser mayor que cero."
            )

        elif "datos" not in st.session_state:
            st.error(
                "Primero consulta Materials Project."
            )

        else:
            nuevos_criterios = {
                "sistemas": sistemas,
                "densidad_max": densidad,
                "corte_min": corte,
                "hull_max": hull,
            }

            st.session_state.resultado = analizar_materiales(
                st.session_state.datos,
                nuevos_criterios,
            )

            st.session_state.criterios = nuevos_criterios

            st.session_state.registros.append({
                "origen": "formulario",
                "fecha_utc": fecha_actual(),
                "criterios": copy.deepcopy(
                    nuevos_criterios
                ),
            })

    st.caption(
        "Los cambios del formulario se aplican "
        "al pulsar «Aplicar filtros»."
    )


# ---------------------------------------------------------
# PANTALLA INICIAL
# ---------------------------------------------------------
if "datos" not in st.session_state:
    st.info(
        "Para comenzar, pulsa «Consultar Materials Project» "
        "en el panel lateral."
    )

    st.write(
        "Después podrás utilizar los filtros o conversar "
        "con Gemini para modificar los criterios."
    )

    st.stop()


# ---------------------------------------------------------
# CRITERIOS Y RESULTADOS
# ---------------------------------------------------------
st.subheader("Criterios aplicados")

st.json(
    st.session_state.criterios
)

st.caption(
    "Los valores iniciales son ilustrativos. "
    "El límite de 0.05 eV/átomo no es un umbral universal "
    "de estabilidad o sintetizabilidad."
)

resultado = st.session_state.resultado

aceptados = resultado.loc[
    resultado["aceptado"]
].copy()

frente = aceptados.loc[
    aceptados["pareto"]
]

col1, col2, col3 = st.columns(3)

col1.metric(
    "Registros descargados",
    len(resultado),
)

col2.metric(
    "Cumplen los criterios",
    len(aceptados),
)

col3.metric(
    "En el frente de Pareto",
    len(frente),
)


# ---------------------------------------------------------
# GRÁFICA DE PARETO
# ---------------------------------------------------------
st.subheader("Densidad y rigidez")

if aceptados.empty:
    st.warning(
        "Ningún material cumple los criterios actuales. "
        "Revisa los motivos de descarte antes de modificar "
        "las restricciones."
    )

else:
    datos_grafica = aceptados.copy()

    datos_grafica["Clasificación"] = (
        datos_grafica["pareto"].map({
            True: "Frente de Pareto",
            False: "Dominado",
        })
    )

    figura = px.scatter(
        datos_grafica,
        x="densidad",
        y="G_VRH",
        color="Clasificación",
        hover_name="formula",
        hover_data=[
            "material_id",
            "E_hull",
            "K_VRH",
        ],
        labels={
            "densidad": "Densidad (g/cm³)",
            "G_VRH": "Módulo de corte VRH (GPa)",
        },
        color_discrete_map={
            "Frente de Pareto": "#00897B",
            "Dominado": "#B0BEC5",
        },
    )

    figura.update_traces(
        marker={"size": 12}
    )

    st.plotly_chart(
        figura,
        use_container_width=True,
    )

    st.caption(
        "Menor densidad hacia la izquierda y mayor rigidez "
        "hacia arriba. El frente se calcula únicamente entre "
        "los candidatos aceptados de esta copia de datos."
    )


# ---------------------------------------------------------
# TABLAS
# ---------------------------------------------------------
tab1, tab2 = st.tabs([
    "Candidatos",
    "Todos los registros y descartes",
])

with tab1:
    st.dataframe(
        aceptados.sort_values(
            ["pareto", "densidad"],
            ascending=[False, True],
        ),
        hide_index=True,
        use_container_width=True,
    )

with tab2:
    st.dataframe(
        resultado,
        hide_index=True,
        use_container_width=True,
    )

st.caption(
    "Unidades: densidad en g/cm³; G_VRH y K_VRH en GPa; "
    "E_hull en eV/átomo. Los datos faltantes no se sustituyen "
    "por valores generados por el modelo."
)


# ---------------------------------------------------------
# DESCARGAS
# ---------------------------------------------------------
st.subheader("Guardar el análisis")

st.download_button(
    "Descargar tabla completa CSV",
    data=resultado.to_csv(
        index=False
    ).encode("utf-8-sig"),
    file_name="materia_resultados.csv",
    mime="text/csv",
)

expediente = {
    "metadata": st.session_state.metadata,
    "criterios": st.session_state.criterios,
    "datos_descargados": registros_json(
        st.session_state.datos
    ),
    "resultados": registros_json(
        resultado
    ),
    "conversacion": st.session_state.mensajes,
    "registros": st.session_state.registros,
}

st.download_button(
    "Descargar expediente JSON",
    data=json.dumps(
        expediente,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ),
    file_name="materia_expediente.json",
    mime="application/json",
)

st.caption(
    "La información se mantiene durante esta sesión. "
    "Descarga el expediente para conservarla. "
    "Esta versión todavía no incluye la recarga del JSON."
)


# ---------------------------------------------------------
# CHAT CON GEMINI
# ---------------------------------------------------------
st.divider()

st.subheader("Conversar con Matéria")

st.caption(
    "Ejemplo: «Busca óxidos con aluminio, densidad máxima "
    "de 4 g/cm³ y módulo de corte mínimo de 80 GPa»."
)

for mensaje in st.session_state.mensajes:
    with st.chat_message(
        mensaje["role"]
    ):
        st.markdown(
            mensaje["content"]
        )

pregunta = st.chat_input(
    "Escribe tu solicitud"
)

if pregunta:
    clave_gemini = secreto(
        "GEMINI_API_KEY"
    )

    modelo = secreto(
        "GEMINI_MODEL",
        "gemini-flash-latest",
    )

    if not clave_gemini:
        st.error(
            "Falta configurar GEMINI_API_KEY. "
            "Los filtros manuales siguen disponibles."
        )

    else:
        try:
            with st.spinner(
                "Gemini está analizando tu solicitud..."
            ):
                (
                    texto,
                    nuevos_criterios,
                    nuevo_resultado,
                    registro,
                ) = conversar(
                    mensaje=pregunta,
                    historial=st.session_state.mensajes,
                    datos=st.session_state.datos,
                    criterios=st.session_state.criterios,
                    api_key=clave_gemini,
                    modelo=modelo,
                )

            registro["fecha_utc"] = fecha_actual()

            st.session_state.mensajes.extend([
                {
                    "role": "user",
                    "content": pregunta,
                },
                {
                    "role": "assistant",
                    "content": texto,
                },
            ])

            st.session_state.criterios = nuevos_criterios

            st.session_state.registros.append(
                registro
            )

            if nuevo_resultado is not None:
                st.session_state.resultado = nuevo_resultado

                st.session_state.revision_formulario += 1

            st.rerun()

        except Exception as error:
            st.error(
                "No se completó la conversación con Gemini. "
                "Comprueba la clave, el modelo y la cuota disponible."
            )

            st.code(
                mensaje_error(
                    error,
                    clave_gemini,
                ),
                language="text",
            )


# ---------------------------------------------------------
# TRAZABILIDAD
# ---------------------------------------------------------
with st.expander(
    "Registro de ejecución"
):
    st.json(
        st.session_state.registros
    )

with st.expander(
    "Procedencia de los datos"
):
    st.json(
        st.session_state.metadata
    )
