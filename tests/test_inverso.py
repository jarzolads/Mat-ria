"""Pruebas offline con datos sintéticos, sin consultas externas."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from inverso import INICIAL, SolicitudInversa, buscar_inverso, descargar_inverso


def tabla():
    return pd.DataFrame([
        dict(material_id='test-A', formula='Fe3O4', sistema='Fe-O', E_hull=0.01, M_vol=0.03, densidad=5., ordenamiento='FiM'),
        dict(material_id='test-B', formula='Fe2O3', sistema='Fe-O', E_hull=0.02, M_vol=0.01, densidad=5., ordenamiento='AFM'),
        dict(material_id='test-C', formula='FeO', sistema='Fe-O', E_hull=0.2, M_vol=0.08, densidad=6., ordenamiento='FM'),
        dict(material_id='test-D', formula='FeO', sistema='Fe-O', E_hull=0.01, M_vol=np.nan, densidad=6., ordenamiento=None),
    ])

class CienciaTest(unittest.TestCase):
    def test_categorias_y_no_relajar_hull(self):
        r = buscar_inverso(tabla(), INICIAL).set_index('material_id')
        self.assertEqual(r.loc['test-A','estado'], 'Cumple objetivos')
        self.assertEqual(r.loc['test-B','estado'], 'Aproximado')
        self.assertAlmostEqual(r.loc['test-B','distancia'], 1.)
        self.assertEqual(r.loc['test-C','estado'], 'Excluido por restricciones')
        self.assertEqual(r.loc['test-D','estado'], 'Sin datos suficientes')
        self.assertTrue(pd.isna(r.loc['test-C','distancia']))
        self.assertTrue(pd.isna(r.loc['test-D','distancia']))

    def test_objetivo_tolerancia_y_pesos(self):
        s = copy.deepcopy(INICIAL)
        s['objetivos'] = [dict(propiedad='M_vol', tipo='objetivo', valor=0.02, escala=0.01, peso=2),
                          dict(propiedad='densidad', tipo='maximo', valor=4., escala=2., peso=1)]
        r = buscar_inverso(tabla(), s).set_index('material_id')
        self.assertAlmostEqual(r.loc['test-A','distancia'], 2.5/3)
        self.assertEqual(r.loc['test-A','estado'], 'Aproximado')
        s['objetivos'] = s['objetivos'][:1]
        self.assertEqual(buscar_inverso(tabla(),s).set_index('material_id').loc['test-A','estado'], 'Cumple objetivos')

    def test_ordenamiento_sistema_y_hull_ausente(self):
        s = copy.deepcopy(INICIAL); s['ordenamientos'] = ['FiM']
        datos=tabla(); datos.loc[0,'sistema']='Fe-Zn-O'; datos.loc[1,'E_hull']=np.nan
        r=buscar_inverso(datos,s).set_index('material_id')
        self.assertEqual(r.loc['test-A','estado'], 'Excluido por restricciones')
        self.assertIn('E_hull ausente',r.loc['test-B','motivos'])
        self.assertEqual(r.loc['test-D','estado'],'Sin datos suficientes')

    def test_validacion(self):
        for field,val in [('escala',0),('peso',-1),('valor',float('inf'))]:
            s=copy.deepcopy(INICIAL);s['objetivos'][0][field]=val
            with self.assertRaises(ValueError): SolicitudInversa.model_validate(s)
        s=copy.deepcopy(INICIAL);s['objetivos']*=2
        with self.assertRaises(ValueError): SolicitudInversa.model_validate(s)

    def test_vacio_y_cero_magnetico(self):
        self.assertTrue(buscar_inverso(tabla().iloc[:0],INICIAL).empty)
        datos=tabla();datos.loc[0,'M_vol']=0
        self.assertEqual(buscar_inverso(datos,INICIAL).set_index('material_id').loc['test-A','estado'],'Aproximado')

    def test_no_modifica_datos_y_determinismo(self):
        datos=tabla(); original=datos.copy(deep=True)
        r=buscar_inverso(datos, INICIAL)
        pd.testing.assert_frame_equal(datos,original)
        pd.testing.assert_frame_equal(r,buscar_inverso(datos.sample(frac=1,random_state=2),INICIAL))

    def test_descarga_preserva_ausentes_y_metadata(self):
        docs=[dict(material_id='test-A',formula_pretty='FeO',chemsys='Fe-O',density=5.,energy_above_hull=0.,
                   ordering='AFM',total_magnetization_normalized_vol=None)]
        with patch('mp_api.client.MPRester') as m:
            m.return_value.__enter__.return_value.materials.summary.search.return_value=docs
            d,meta=descargar_inverso('clave-ficticia',['Fe-O'])
            self.assertTrue(pd.isna(d.loc[0,'M_vol']))
            self.assertEqual(meta['unidades']['M_vol'],'μB/Å³')
            self.assertNotIn('clave-ficticia',json.dumps(meta))

class AgenteTest(unittest.TestCase):
    def test_llama_herramienta_y_conserva_estado(self):
        from google.genai import types
        from agente import conversar
        def response(part):
            return SimpleNamespace(usage_metadata=None,model_version='test',
                                   candidates=[SimpleNamespace(content=types.Content(role='model',parts=[part]))])
        resp1=response(types.Part(function_call=types.FunctionCall(name='buscar_materiales_inverso',args=INICIAL)))
        resp2=response(types.Part.from_text(text='Resultado de prueba.'))
        with patch('agente.genai.Client') as cliente:
            cliente.return_value.__enter__.return_value.models.generate_content.side_effect=[resp1,resp2]
            texto,s,r,log=conversar('buscar',[],tabla(),INICIAL,'no-real','test',modo='inverso',sistemas_disponibles=['Fe-O'])
        self.assertEqual(texto,'Resultado de prueba.')
        self.assertEqual(len(r),4)
        self.assertEqual(log['trazas'][0]['salida']['conteos']['Cumple objetivos'],1)
        self.assertEqual(s,INICIAL)

    def test_rechaza_sistema_no_descargado(self):
        from google.genai import types
        from agente import conversar
        otra=copy.deepcopy(INICIAL);otra['sistemas']=['Fe-Zn-O']
        content=types.Content(role='model',parts=[types.Part(function_call=types.FunctionCall(name='buscar_materiales_inverso',args=otra))])
        respuesta=SimpleNamespace(usage_metadata=None,model_version='test',candidates=[SimpleNamespace(content=content)])
        with patch('agente.genai.Client') as c:
            c.return_value.__enter__.return_value.models.generate_content.return_value=respuesta
            _,s,r,log=conversar('buscar',[],tabla(),INICIAL,'x','test',modo='inverso',sistemas_disponibles=['Fe-O'])
        self.assertIsNone(r)
        self.assertEqual(s,INICIAL)
        self.assertIn('error',log['trazas'][0]['salida'])

if __name__=='__main__': unittest.main()
