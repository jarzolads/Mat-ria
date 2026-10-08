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

## Nuevo modo: búsqueda inversa

En el panel lateral elige **Búsqueda inversa**. El modo original
**Explorar óxidos** sigue disponible, con su copia y conversación separadas.
Esta etapa selecciona materiales existentes; no genera nuevas composiciones.

1. Descarga Fe–O (o Fe–Mg–O, Fe–Mn–O, Fe–Zn–O) desde el panel.
2. Define E_hull máximo y, opcionalmente, ordenamientos permitidos.
3. Activa una o más propiedades objetivo: M_vol (μB/Å³), densidad (g/cm³)
   o E_hull (eV/átomo). Cada propiedad admite mínimo, máximo o valor objetivo.
4. Define escala/tolerancia positiva y peso positivo; ejecuta la búsqueda.
5. Revisa las cuatro categorías: cumple objetivos, aproximado, sin datos
   suficientes y excluido por restricciones.
6. Descarga CSV y JSON; el servidor no persiste automáticamente la sesión.

Ejemplo de chat, después de descargar Fe–O:

> Mantén Fe–O y E_hull máximo 0.05 eV/átomo. Pide M_vol mínimo de
> 0.03 μB/Å³, con escala 0.01 y peso 1. No filtres ordenamiento.

Las cifras iniciales son ejemplos de interacción, no requisitos para hipertermia.
Los sistemas que no fueron descargados se rechazan en la herramienta. Para
ampliar la búsqueda, descarga esos sistemas primero. La descarga inicia un
expediente nuevo; exporta antes el anterior si deseas conservarlo.

### Distancia y restricciones

Distancia = suma(peso × desviación/escala) / suma(pesos).

- Mínimo: desviación = max(objetivo − valor, 0).
- Máximo: desviación = max(valor − objetivo, 0).
- Valor objetivo: desviación = abs(valor − objetivo); cumple si está dentro
  de ± escala (tolerancia absoluta en la unidad de la propiedad).
- En mínimos/máximos, escala normaliza y **no** flexibiliza el umbral.
- Sistemas, E_hull máximo y ordenamientos son restricciones duras.
- Un dato requerido ausente/no válido no recibe distancia; no se imputa cero.
- Se ordena primero por categoría y después por distancia e identificador.
  Esta distancia no es una probabilidad ni un índice de eficacia biomédica.
- Un candidato excluido puede tener también datos ausentes: se conservan todos
  los motivos aunque su categoría principal sea exclusión.
- La gráfica M_vol–E_hull es descriptiva, no un frente de Pareto de desempeño térmico.

### Alcance científico

Se consulta `materials.summary` sin exigir datos elásticos ni aplicar el filtro
Al(+3)/Mg(+2) del modo original. Son registros de los sistemas químicos elegidos;
la estequiometría o fase no se certifica automáticamente como ferrita.

La magnetización y el ordenamiento corresponden a cálculos de cristales. No se
calculan SAR, SLP, tamaño de nanopartícula, superparamagnetismo, magnetización de
saturación experimental ni biocompatibilidad. El ordenamiento reportado puede
describir la configuración calculada y no el estado fundamental real. Una mayor
magnetización no implica mejor desempeño en hipertermia.

Fuentes metodológicas:

- https://docs.materialsproject.org/methodology/materials-methodology/magnetic-properties
- https://materialsproject.github.io/api/_autosummary/mp_api.client.routes.materials.summary.SummaryRester.html

### Activar la actualización en Streamlit

No se necesitan secretos adicionales: se usan MP_API_KEY, GEMINI_API_KEY y
GEMINI_MODEL existentes. Una vez integrado el cambio en la rama desplegada,
Streamlit vuelve a ejecutar `app.py`; elige **Búsqueda inversa** en la barra lateral.
Conserva el modelo de Gemini configurado en tu aplicación.

### Verificación

Ejecutar desde la raíz:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Las pruebas utilizan datos sintéticos y respuestas simuladas, sin claves ni
consumo de API. Cubren restricciones, tolerancias, pesos, ausentes, ordenamiento,
validación de argumentos, determinismo, lectura de metadatos y llamadas de Gemini.
La conexión real a Materials Project y Gemini requiere las claves del despliegue.

Para reproducibilidad: conserva el expediente con hash, campos, unidades,
versiones, fecha, copia de datos, solicitud y trazas. Fija las dependencias tras
validar tu despliegue y usa un identificador de modelo concreto para el experimento.
