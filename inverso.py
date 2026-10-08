"""Búsqueda inversa sobre registros MP, sin generación ni predicción de SAR."""
import hashlib
import json
from datetime import datetime, timezone
from importlib.metadata import version
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

SISTEMAS_INVERSOS = ['Fe-O', 'Fe-Mg-O', 'Fe-Mn-O', 'Fe-Zn-O']
PROPIEDADES = {
    'M_vol': 'Magnetización calculada por volumen (μB/Å³)',
    'densidad': 'Densidad (g/cm³)',
    'E_hull': 'Energía sobre la envolvente (eV/átomo)',
}
ORDENES = ['FM', 'FiM', 'AFM', 'NM', 'Unknown']
INICIAL = {
    'sistemas': ['Fe-O'], 'hull_max': 0.05, 'ordenamientos': [],
    'objetivos': [{'propiedad': 'M_vol', 'tipo': 'minimo',
                   'valor': 0.02, 'escala': 0.01, 'peso': 1.0}],
}

class Objetivo(BaseModel):
    model_config = ConfigDict(extra='forbid')
    propiedad: Literal['M_vol', 'densidad', 'E_hull']
    tipo: Literal['minimo', 'maximo', 'objetivo']
    valor: float = Field(ge=0, allow_inf_nan=False)
    escala: float = Field(gt=0, allow_inf_nan=False)
    peso: float = Field(gt=0, allow_inf_nan=False)

class SolicitudInversa(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sistemas: list[Literal['Fe-O', 'Fe-Mg-O', 'Fe-Mn-O', 'Fe-Zn-O']] = Field(min_length=1)
    hull_max: float = Field(ge=0, allow_inf_nan=False)
    ordenamientos: list[Literal['FM', 'FiM', 'AFM', 'NM', 'Unknown']]
    objetivos: list[Objetivo] = Field(min_length=1, max_length=3)

    @model_validator(mode='after')
    def sin_repetidos(self):
        props = [o.propiedad for o in self.objetivos]
        if len(props) != len(set(props)):
            raise ValueError('Cada propiedad puede aparecer una sola vez.')
        return self


def descargar_inverso(api_key, sistemas):
    """Consulta explícita: conserva ausentes y no filtra ordenamiento en origen."""
    from mp_api.client import MPRester
    if not sistemas or not set(sistemas).issubset(SISTEMAS_INVERSOS):
        raise ValueError('Selecciona sistemas químicos admitidos.')
    campos = ['material_id', 'formula_pretty', 'chemsys', 'density',
              'energy_above_hull', 'ordering', 'total_magnetization_normalized_vol',
              'symmetry', 'last_updated']
    with MPRester(api_key, use_document_model=False) as mpr:
        docs = mpr.materials.summary.search(
            chemsys=sorted(set(sistemas)), deprecated=False, fields=campos)
    if not docs:
        raise ValueError('La consulta no devolvió materiales; se conserva el análisis anterior.')
    filas = []
    for d in docs:
        orden = d.get('ordering')
        orden = getattr(orden, 'value', orden)
        filas.append({
            'material_id': str(d['material_id']), 'formula': d['formula_pretty'],
            'sistema': d['chemsys'], 'densidad': d.get('density'),
            'E_hull': d.get('energy_above_hull'),
            'M_vol': d.get('total_magnetization_normalized_vol'),
            'ordenamiento': orden,
            'grupo_espacial': (d.get('symmetry') or {}).get('symbol'),
            'actualizado_mp': str(d.get('last_updated') or ''),
        })
    datos = pd.DataFrame(filas).drop_duplicates('material_id').reset_index(drop=True)
    for c in PROPIEDADES:
        datos[c] = pd.to_numeric(datos[c], errors='coerce')
    serial = datos.sort_values('material_id').to_json(orient='records', double_precision=15)
    meta = {
        'fuente': 'Materials Project / materials.summary',
        'fecha_utc': datetime.now(timezone.utc).isoformat(),
        'sistemas_consultados': sorted(set(sistemas)), 'campos': campos,
        'deprecated': False, 'sha256_tabla': hashlib.sha256(serial.encode()).hexdigest(),
        'unidades': {'M_vol': 'μB/Å³', 'densidad': 'g/cm³', 'E_hull': 'eV/átomo'},
        'versiones': {p: version(p) for p in ['mp-api', 'pandas', 'numpy', 'pydantic']},
        'limite': 'Cristales calculados; no son nanopartículas ni datos de calentamiento o biocompatibilidad.',
    }
    return datos, meta


def buscar_inverso(datos, solicitud):
    """Restricciones duras separadas de la distancia normalizada a objetivos."""
    s = SolicitudInversa.model_validate(solicitud)
    columnas = ['material_id', 'formula', 'sistema', 'E_hull', 'ordenamiento']
    columnas += [o.propiedad for o in s.objetivos]
    faltan = set(columnas) - set(datos.columns)
    if faltan:
        raise ValueError(f'Faltan columnas: {sorted(faltan)}')
    salida = datos.copy()
    evaluaciones = []
    for _, fila in salida.iterrows():
        restricciones, ausentes, incumple = [], [], []
        detalles = {}
        if fila['sistema'] not in s.sistemas:
            restricciones.append('Sistema fuera de la selección')
        hull = pd.to_numeric(fila['E_hull'], errors='coerce')
        if pd.isna(hull) or not np.isfinite(hull) or hull < 0:
            ausentes.append('E_hull ausente/no válido')
        elif hull > s.hull_max:
            restricciones.append('E_hull supera la restricción dura')
        if s.ordenamientos:
            if pd.isna(fila['ordenamiento']) or not str(fila['ordenamiento']).strip():
                ausentes.append('Ordenamiento ausente')
            elif fila['ordenamiento'] not in s.ordenamientos:
                restricciones.append('Ordenamiento fuera de la selección')
        distancias = []
        for o in s.objetivos:
            valor = pd.to_numeric(fila[o.propiedad], errors='coerce')
            if (pd.isna(valor) or not np.isfinite(valor) or valor < 0
                    or (o.propiedad == 'densidad' and valor == 0)):
                ausentes.append(f'{o.propiedad} ausente/no válido')
                detalles[f'desviacion_{o.propiedad}'] = np.nan
                continue
            if o.tipo == 'minimo':
                desviacion = max(o.valor - valor, 0.0)
                cumple = valor >= o.valor
            elif o.tipo == 'maximo':
                desviacion = max(valor - o.valor, 0.0)
                cumple = valor <= o.valor
            else:
                desviacion = abs(valor - o.valor)
                cumple = desviacion <= o.escala + 1e-12
            detalles[f'desviacion_{o.propiedad}'] = float(desviacion)
            distancias.append(o.peso * desviacion / o.escala)
            if not cumple:
                incumple.append(f'{o.propiedad}: no cumple {o.tipo} {o.valor}')
        if restricciones:
            estado = 'Excluido por restricciones'
        elif ausentes:
            estado = 'Sin datos suficientes'
        elif incumple:
            estado = 'Aproximado'
        else:
            estado = 'Cumple objetivos'
        puntuacion = (sum(distancias) / sum(o.peso for o in s.objetivos)
                      if not restricciones and not ausentes else np.nan)
        evaluaciones.append({**detalles, 'estado': estado, 'distancia': puntuacion,
                             'motivos': '; '.join(restricciones + ausentes + incumple)})
    # Mantiene el esquema incluso con tablas vacías.
    for c in ['estado', 'distancia', 'motivos'] + [f'desviacion_{o.propiedad}' for o in s.objetivos]:
        salida[c] = [e.get(c, np.nan) for e in evaluaciones]
    orden = {'Cumple objetivos': 0, 'Aproximado': 1,
             'Sin datos suficientes': 2, 'Excluido por restricciones': 3}
    return (salida.assign(_orden=salida['estado'].map(orden))
            .sort_values(['_orden', 'distancia', 'material_id'], na_position='last')
            .drop(columns='_orden').reset_index(drop=True))


def resumen_inverso(resultado, solicitud):
    vista = resultado.head(40)
    return {
        'solicitud': solicitud, 'conteos': resultado['estado'].value_counts().to_dict(),
        'total': len(resultado), 'vista_parcial': len(resultado) > 40,
        'registros': json.loads(vista.to_json(orient='records', double_precision=15)),
        'advertencia': 'Distancia menor significa cercanía a los objetivos, no eficacia para hipertermia. '
                       'Los aproximados NO cumplen todos los objetivos. No se relajan restricciones duras.',
    }
