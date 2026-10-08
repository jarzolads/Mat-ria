import copy
from datetime import datetime, timezone

import streamlit as st

from agente import conversar
from inverso import INICIAL, descargar_inverso


EJEMPLO = (
    "Busca óxidos de hierro en Fe-O con magnetización "
    "calculada por volumen mínima de 0.02 μB/Å³ y energía "
    "sobre la envolvente máxima de 0.05 eV/átomo. "
    "No filtres por ordenamiento. Usa escala 0.01 y peso 1."
)


def mostrar_inverso():

    if "inv_solicitud" not in st.session_state:
        st.session_state.inv_solicitud = copy.deepcopy(INICIAL)

    if "inv_mensajes" not in st.session_state:
        st.session_state.inv_mensajes = []

    if "inv_registros" not in st.session_state:
        st.session_state.inv_registros = []

    def secreto(nombre, valor_default=""):
        try:
            return st.secrets.get(nombre, valor_default)
        except FileNotFoundError:
            return valor_default

    st.title("Matéria: demostración de diseño inverso")

    st.write(
        "Define las propiedades deseadas y el agente buscará "
        "materiales existentes que se aproximen a ellas."
    )

    st.info(
        "Esta demostración utiliza datos de Materials Project. "
        "Busca registros existentes; no genera materiales nuevos."
    )

    st.subheader("Demostración")

    st.write(
        "Primero pediremos un óxido de hierro con cierta "
        "magnetización y estabilidad calculada."
    )

    col1, col2, col3 = st.columns(3)

    pregunta = None

    if col1.button("Probar ejemplo", use_container_width=True):
        pregunta = EJEMPLO

    if col2.button(
        "Pedir más magnetización",
        disabled="inv_resultado" not in st.session_state,
        use_container_width=True,
    ):
        pregunta = (
            "Aumenta la magnetización mínima a "
            "0.04 μB/Å³ y conserva los demás criterios."
        )

    if col3.button(
        "Añadir baja densidad",
        disabled="inv_resultado" not in st.session_state,
        use_container_width=True,
    ):
        pregunta = (
            "Añade una densidad máxima de 5 g/cm³ "
            "y conserva los demás criterios."
        )

    pregunta_chat = st.chat_input(
        "Escribe las propiedades que deseas"
    )

    if pregunta_chat:
        pregunta = pregunta_chat

    if pregunta:

        clave_mp = secreto("MP_API_KEY")
        clave_gemini = secreto("GEMINI_API_KEY")
        modelo = secreto(
            "GEMINI_MODEL",
            "gemini-flash-latest",
        )

        if not clave_mp or not clave_gemini:
            st.error(
                "Configura MP_API_KEY y GEMINI_API_KEY "
                "en los secretos de Streamlit."
            )
            st.stop()

        try:

            if "inv_datos" not in st.session_state:

                with st.spinner(
                    "Consultando Materials Project..."
                ):
                    datos, metadata = descargar_inverso(
                        clave_mp,
                        ["Fe-O"],
                    )

                st.session_state.inv_datos = datos
                st.session_state.inv_metadata = metadata

            with st.spinner(
                "Gemini interpreta la solicitud..."
            ):

                texto, nueva_solicitud, resultado, registro = conversar(
                    mensaje=pregunta,
                    historial=st.session_state.inv_mensajes,
                    datos=st.session_state.inv_datos,
                    criterios=st.session_state.inv_solicitud,
                    api_key=clave_gemini,
                    modelo=modelo,
                    modo="inverso",
                    sistemas_disponibles=["Fe-O"],
                )

            st.session_state.inv_solicitud = nueva_solicitud
            st.session_state.inv_resultado = resultado

            st.session_state.inv_mensajes.extend(
                [
                    {
                        "role": "user",
                        "content": pregunta,
                    },
                    {
                        "role": "assistant",
                        "content": texto,
                    },
                ]
            )

            registro["fecha_utc"] = datetime.now(
                timezone.utc
            ).isoformat()

            st.session_state.inv_registros.append(
                registro
            )

        except Exception as error:
            texto_error = str(error)

            for clave in [clave_mp, clave_gemini]:
                if clave:
                    texto_error = texto_error.replace(
                        clave,
                        "[CLAVE OCULTA]",
                    )

            st.error(
                f"No se pudo completar la consulta: "
                f"{type(error).__name__}: {texto_error}"
            )

    if st.session_state.inv_mensajes:

        st.subheader("Conversación")

        for mensaje in st.session_state.inv_mensajes:
            with st.chat_message(
                mensaje["role"]
            ):
                st.markdown(
                    mensaje["content"]
                )

    if "inv_resultado" not in st.session_state:

        st.info(
            "Pulsa «Probar ejemplo» para iniciar "
            "la demostración."
        )

        with st.expander(
            "¿Qué demuestra este agente?"
        ):
            st.write(
                "El usuario comienza con propiedades deseadas. "
                "Gemini convierte la petición en criterios "
                "estructurados. Python compara esos criterios "
                "con los datos de Materials Project y devuelve "
                "los candidatos encontrados."
            )

        return

    resultado = st.session_state.inv_resultado

    completos = resultado[
        resultado["estado"] == "Cumple objetivos"
    ]

    aproximados = resultado[
        resultado["estado"] == "Aproximado"
    ]

    st.subheader("Candidatos encontrados")

    col1, col2 = st.columns(2)

    col1.metric(
        "Cumplen los objetivos",
        len(completos),
    )

    col2.metric(
        "Candidatos aproximados",
        len(aproximados),
    )

    if completos.empty:
        st.warning(
            "No hay coincidencias completas. "
            "Los candidatos aproximados incumplen "
            "algún objetivo."
        )

    vista = resultado[
        resultado["estado"].isin(
            [
                "Cumple objetivos",
                "Aproximado",
            ]
        )
    ].head(5)

    if not vista.empty:

        st.dataframe(
            vista[
                [
                    "formula",
                    "material_id",
                    "M_vol",
                    "densidad",
                    "E_hull",
                    "estado",
                    "motivos",
                ]
            ],
            hide_index=True,
            use_container_width=True,
        )

    st.caption(
        "Los valores corresponden a materiales calculados "
        "en Materials Project. No representan directamente "
        "SAR, calentamiento de nanopartículas ni biocompatibilidad."
    )

    with st.expander(
        "Ver solicitud y registro técnico"
    ):

        st.write("Solicitud interpretada por el agente:")
        st.json(
            st.session_state.inv_solicitud
        )

        st.write("Tabla completa:")
        st.dataframe(
            resultado,
            hide_index=True,
            use_container_width=True,
        )

        st.write("Registro de ejecución:")
        st.json(
            st.session_state.inv_registros
        )
