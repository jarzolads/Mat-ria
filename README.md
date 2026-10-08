# Matéria

Agente con Gemini e interfaz de Streamlit para el cribado
multicriterio de óxidos.

## Alcance

Sistemas químicos:

- Al–O.
- Mg–O.
- Al–Mg–O.

La definición composicional inicial considera materiales
compatibles con Al(+3), Mg(+2) y O(-2). No demuestra los estados
de oxidación reales.

## Funciones

- Consulta de datos de Materials Project.
- Filtros de densidad, módulo de corte y energía sobre la envolvente.
- Cálculo del frente de Pareto.
- Chat con Gemini mediante llamadas a herramientas.
- Exportación de resultados y registro de ejecución.

## Objetivos del análisis

- Minimizar densidad.
- Maximizar módulo de corte VRH.
- Aplicar un límite configurable de energía sobre la envolvente.

## Archivos

- app.py: interfaz.
- ciencia.py: consulta y análisis científico.
- agente.py: integración con Gemini.
- requirements.txt: dependencias.

## Configuración

Configurar estos secretos en Streamlit Community Cloud:

- MP_API_KEY
- GEMINI_API_KEY
- GEMINI_MODEL

No guardar claves reales en el repositorio.

## Limitaciones

- Los resultados son una selección computacional preliminar.
- La disponibilidad de propiedades depende de Materials Project.
- Un módulo de corte alto no demuestra alta dureza.
- La energía sobre la envolvente no garantiza sintetizabilidad.
- El frente de Pareto depende de los datos y filtros utilizados.
- Un módulo de corte positivo no demuestra por sí solo estabilidad
  mecánica mediante el tensor elástico completo.
- Las explicaciones del modelo deben contrastarse con las tablas.
- El expediente se exporta, pero esta versión no permite recargarlo.
- Para experimentos reproducibles deben fijarse versiones de
  dependencias, modelo y copia de datos.
