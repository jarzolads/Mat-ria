"""Interfaz de búsqueda inversa; estado separado del explorador original."""
import copy
import json
from datetime import datetime, timezone

import plotly.express as px
import streamlit as st

from agente import conversar
from inverso import (INICIAL, ORDENES, PROPIEDADES, SISTEMAS_INVERSOS,
                     SolicitudInversa, buscar_inverso, descargar_inverso)


def mostrar_inverso():
    ss = st.session_state
    for k, v in {'inv_solicitud': INICIAL, 'inv_mensajes': [], 'inv_registros': [], 'inv_rev': 0}.items():
        if k not in ss:
            ss[k] = copy.deepcopy(v)
    def secreto(k, default=''):
        try:
            return st.secrets.get(k, default)
        except FileNotFoundError:
            return default
    def error_publico(e):
        texto = str(e)
        for clave in [secreto('MP_API_KEY'), secreto('GEMINI_API_KEY')]:
            if clave:
                texto = texto.replace(clave, '[CLAVE OCULTA]')
        st.error(f'{type(e).__name__}: {texto}')

    st.title('Matéria · Búsqueda inversa')
    st.write('Define propiedades deseadas y encuentra registros de Materials Project que cumplen o se aproximan.')
    st.info('Se buscan materiales registrados; no se generan composiciones nuevas. '
            'La magnetización calculada del cristal no predice SAR, superparamagnetismo ni biocompatibilidad.')
    with st.sidebar:
        st.subheader('Copia de datos')
        sistemas_carga = st.multiselect('Sistemas para descargar', SISTEMAS_INVERSOS,
                                       default=['Fe-O'], key='inv_carga_sistemas')
        if st.button('Descargar materiales magnéticos', key='inv_cargar'):
            if not secreto('MP_API_KEY'):
                st.error('Configura MP_API_KEY en Secrets.')
            else:
                try:
                    with st.spinner('Consultando Materials Project…'):
                        datos, meta = descargar_inverso(secreto('MP_API_KEY'), sistemas_carga)
                    solicitud = copy.deepcopy(ss.inv_solicitud)
                    solicitud['sistemas'] = meta['sistemas_consultados']
                    resultado = buscar_inverso(datos, solicitud)
                    ss.inv_datos, ss.inv_meta = datos, meta
                    ss.inv_solicitud, ss.inv_resultado = solicitud, resultado
                    ss.inv_mensajes = []
                    ss.inv_registros = [{'evento': 'descarga', 'metadata': meta, 'solicitud': solicitud}]
                    ss.inv_rev += 1
                    st.success(f'{len(datos)} registros descargados.')
                except Exception as e:
                    error_publico(e)
    if 'inv_datos' not in ss:
        st.write('Descarga primero uno o más sistemas. Puedes usar el formulario sin activar Gemini.')
        st.caption('Los objetivos iniciales son ejemplos numéricos, no requisitos biomédicos.')
        return

    solicitud = ss.inv_solicitud
    with st.expander('Definir objetivos y restricciones', expanded=True):
        with st.form(f'inv_form_{ss.inv_rev}'):
            sistemas = st.multiselect('Sistemas incluidos en la búsqueda', ss.inv_meta['sistemas_consultados'],
                                     default=solicitud['sistemas'])
            hull = st.number_input('Restricción dura: E_hull máximo (eV/átomo)', min_value=0.0,
                                   value=float(solicitud['hull_max']), format='%.5f')
            ordenes = st.multiselect('Ordenamientos permitidos (vacío = sin filtro)', ORDENES,
                                    default=solicitud['ordenamientos'])
            filas = []
            anteriores = {o['propiedad']: o for o in solicitud['objetivos']}
            for prop, etiqueta in PROPIEDADES.items():
                previo = anteriores.get(prop, {'tipo': 'objetivo', 'valor': 0.0,
                                               'escala': 0.01 if prop != 'densidad' else 1.0, 'peso': 1.0})
                activo = st.checkbox(etiqueta, value=prop in anteriores, key=f'inv_act_{prop}_{ss.inv_rev}')
                cols = st.columns(4)
                tipos = ['minimo', 'maximo', 'objetivo']
                tipo = cols[0].selectbox('Criterio', tipos, index=tipos.index(previo['tipo']), key=f't_{prop}_{ss.inv_rev}')
                valor = cols[1].number_input('Valor deseado', min_value=0.0, value=float(previo['valor']),
                                             format='%.6f', key=f'v_{prop}_{ss.inv_rev}')
                escala = cols[2].number_input('Escala / tolerancia', min_value=0.0,
                                              value=float(previo['escala']), format='%.6f', key=f'e_{prop}_{ss.inv_rev}')
                peso = cols[3].number_input('Peso', min_value=0.0, value=float(previo['peso']),
                                            key=f'p_{prop}_{ss.inv_rev}')
                if activo:
                    filas.append(dict(propiedad=prop, tipo=tipo, valor=valor, escala=escala, peso=peso))
            st.caption('Para un valor objetivo, la escala es la tolerancia ±. Para mínimos/máximos, '
                       'normaliza la desviación sin relajar el umbral. Todos los valores usan las unidades de la etiqueta.')
            aplicar = st.form_submit_button('Ejecutar búsqueda inversa')
        if aplicar:
            try:
                nueva = SolicitudInversa(sistemas=sistemas, hull_max=hull,
                                         ordenamientos=ordenes, objetivos=filas).model_dump()
                resultado = buscar_inverso(ss.inv_datos, nueva)
                ss.inv_solicitud, ss.inv_resultado = nueva, resultado
                ss.inv_registros.append({'evento': 'formulario', 'solicitud': nueva,
                                        'fecha_utc': datetime.now(timezone.utc).isoformat()})
            except ValueError as e:
                st.error(str(e))
    st.subheader('Solicitud aplicada')
    st.json(ss.inv_solicitud, expanded=False)
    resultado = ss.inv_resultado
    categorias = ['Cumple objetivos', 'Aproximado', 'Sin datos suficientes', 'Excluido por restricciones']
    for col, categoria in zip(st.columns(4), categorias):
        col.metric(categoria, int(resultado['estado'].eq(categoria).sum()))
    if not resultado['estado'].eq('Cumple objetivos').any():
        st.warning('No hay coincidencias completas. Los aproximados incumplen algún objetivo; las restricciones duras se mantienen.')
    for tab, categoria in zip(st.tabs(categorias), categorias):
        with tab:
            st.dataframe(resultado[resultado['estado'].eq(categoria)], hide_index=True, width='stretch')
    graficables = resultado[resultado['estado'].isin(categorias[:2])].dropna(subset=['M_vol', 'E_hull'])
    if not graficables.empty:
        fig = px.scatter(graficables, x='E_hull', y='M_vol', color='estado', hover_name='formula',
                         hover_data=['material_id', 'distancia'], labels=PROPIEDADES)
        st.plotly_chart(fig, width='stretch')
    with st.expander('Cómo interpretar la distancia'):
        st.write('La distancia es Σ(peso × desviación/escala) / Σ(pesos). Para mínimos y máximos, '
                 'la desviación es solo la parte que incumple el umbral. Para un objetivo, es el error absoluto. '
                 'Las coincidencias completas aparecen antes que los aproximados; cada grupo se ordena '
                 'por distancia. Un dato ausente no recibe puntuación. No es una probabilidad ni un índice de eficacia.')
        st.write('E_hull y ordenamiento actúan como restricciones duras. La selección no demuestra '
                 'sintetizabilidad, seguridad ni capacidad de calentamiento. El ordenamiento reportado '
                 'puede describir una configuración calculada y no necesariamente el estado fundamental real.')
    def registros(df):
        return json.loads(df.to_json(orient='records', double_precision=15))
    expediente = {'modo': 'busqueda_inversa', 'metadata': ss.inv_meta, 'solicitud': ss.inv_solicitud,
                  'datos': registros(ss.inv_datos), 'resultados': registros(resultado),
                  'conversacion': ss.inv_mensajes, 'registros': ss.inv_registros}
    st.download_button('Descargar resultados CSV', resultado.to_csv(index=False).encode('utf-8-sig'),
                       'materia_inverso.csv', 'text/csv')
    st.download_button('Descargar expediente JSON', json.dumps(expediente, ensure_ascii=False, indent=2,
                                                              allow_nan=False),
                       'materia_inverso.json', 'application/json')
    st.caption('Descarga el expediente antes de cerrar la sesión; no se guarda automáticamente en el servidor.')
    st.subheader('Chat de búsqueda inversa')
    st.caption('Ejemplo: «Mantén los sistemas y pide M_vol mínimo de 0.03 μB/Å³, con escala 0.01 y peso 1».')
    for mensaje in ss.inv_mensajes:
        with st.chat_message(mensaje['role']):
            st.markdown(mensaje['content'])
    pregunta = st.chat_input('Describe tus propiedades objetivo', key='inv_chat')
    if pregunta:
        if not secreto('GEMINI_API_KEY'):
            st.error('Configura GEMINI_API_KEY. El formulario no necesita Gemini.')
        else:
            try:
                with st.spinner('Gemini consulta las herramientas…'):
                    texto, nueva, nuevo_resultado, registro = conversar(
                        pregunta, ss.inv_mensajes, ss.inv_datos, ss.inv_solicitud,
                        secreto('GEMINI_API_KEY'), secreto('GEMINI_MODEL', 'gemini-flash-latest'),
                        modo='inverso', sistemas_disponibles=ss.inv_meta['sistemas_consultados'])
                ss.inv_mensajes.extend([{'role': 'user', 'content': pregunta}, {'role': 'assistant', 'content': texto}])
                registro['fecha_utc'] = datetime.now(timezone.utc).isoformat()
                ss.inv_registros.append(registro)
                if nuevo_resultado is not None:
                    ss.inv_solicitud, ss.inv_resultado = nueva, nuevo_resultado
                    ss.inv_rev += 1
                st.rerun()
            except Exception as e:
                error_publico(e)
    with st.expander('Procedencia y trazas'):
        st.json(ss.inv_meta)
        st.json(ss.inv_registros)
