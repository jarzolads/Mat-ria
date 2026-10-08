import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from inverso import INICIAL, buscar_inverso
from test_inverso import tabla


class InterfazTest(unittest.TestCase):
    def test_cambio_de_modo_y_formulario(self):
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
        self.assertFalse(at.exception)
        at.sidebar.radio[0].set_value('Búsqueda inversa').run(timeout=30)
        self.assertFalse(at.exception)
        at.session_state['inv_datos'] = tabla()
        at.session_state['inv_meta'] = {'sistemas_consultados': ['Fe-O'], 'fuente': 'TEST SINTETICO'}
        at.session_state['inv_resultado'] = buscar_inverso(tabla(), INICIAL)
        at.run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual([m.value for m in at.metric], ['1', '1', '1', '1'])
        at.button(key='FormSubmitter:inv_form_0-Ejecutar búsqueda inversa').click().run(timeout=30)
        self.assertFalse(at.exception)
        at.sidebar.radio[0].set_value('Explorar óxidos').run(timeout=30)
        self.assertFalse(at.exception)
