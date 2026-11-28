"""v1.1: sugerencia de IA local en TITULO_AREA (sin cambiar resultados) y nivel de FORMACION deducido del texto.

Embedder falso: rápido y sin el modelo real. Solo la base de pruebas aislada.
"""
from datetime import date
from unittest.mock import patch

import numpy as np
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from perfiles.models import Area, Formacion, Pais, Perfil, PerfilArea
from .comparacion import ETIQUETA_SUGERENCIA, UMBRAL_SUGERENCIA_TITULO, evaluar_convocatoria, nivel_deducido, nivel_titulo_deducido
from .models import Convocatoria, Institucion, OpcionEstudio, Requisito, TipoRequisito
from .recomendaciones import recomendar
from .reglas import CONTRATOS
from .semantica import ModeloNoDisponible


def unitario(*v):
    v = np.asarray(v, dtype=np.float32)
    return tuple((v / np.linalg.norm(v)).tolist())


def falso(texto):
    """«sistemas/software» apuntan al mismo eje; «medicina», a otro; el resto, a un tercero."""
    t = texto.lower()
    if "sistemas" in t or "software" in t:
        return unitario(1, 0, 0)
    if "medicina" in t:
        return unitario(0, 1, 0)
    return unitario(0, 0, 1)


def sin_sugerencias(data):
    for opcion in data["opciones"]:
        for alternativa in opcion["resultados_destino"]:
            for e in alternativa["requisitos"]:
                e.pop("sugerencia", None)
    data.pop("calculado_en")
    return data


@patch("convocatorias.semantica.vector", side_effect=falso)
@patch("convocatorias.semantica.vector_convocatoria", side_effect=falso)
class SugerenciaTituloTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        cls.area = Area.objects.create(nombre="Tecnologías de prueba")
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        cls.user = get_user_model().objects.create_user(email="sugerencia@example.com", nombre="DEMO", password=None)
        cls.perfil = Perfil.objects.create(usuario=cls.user, nacionalidad=cls.ec, fecha_nacimiento=date(2000, 6, 15))
        PerfilArea.objects.create(perfil=cls.perfil, area=cls.area)
        Formacion.objects.create(perfil=cls.perfil, nivel="grado", carrera="Ingeniería de Software", titulo_obtenido=True,
                                 estado_estudios="concluidos", nombre_titulo="Ingeniero de Software", area=cls.area)
        institucion = Institucion.objects.create(nombre="DEMO entidad", sector="publico", pais=cls.ec)
        cls.conv = Convocatoria.objects.create(institucion=institucion, titulo="DEMO sugerencia", revision="validada", clave_deduplicacion="sugerencia")
        OpcionEstudio.objects.create(convocatoria=cls.conv, nivel="maestria", modalidad="virtual").paises.add(cls.ec)

    def setUp(self):
        self.client = APIClient()
        self.client.force_login(self.user)

    def regla(self, codigo, valor, texto="DEMO condición", **kwargs):
        kwargs.setdefault("validado", True)
        return Requisito.objects.create(convocatoria=self.conv, tipo_requisito=TipoRequisito.objects.get(codigo=codigo),
            texto_original=texto, valor_estructurado=valor, operador=CONTRATOS[codigo][1],
            modo_comprobacion="entidad_oferente" if codigo in ("DOCUMENTO", "ACREDITACION", "OTRO") else "dato_declarado", **kwargs)

    def requisitos(self):
        response = self.client.get(f"/api/becas/{self.conv.pk}/comparacion/")
        self.assertEqual(response.status_code, 200)
        return {e["id"]: e for e in response.data["opciones"][0]["requisitos"]}

    def test_sugerencia_sobre_el_umbral_sin_cambiar_el_resultado(self, *_):
        r = self.regla("TITULO_AREA", {"titulos_admitidos": ["Ingeniería en Sistemas"]})
        e = self.requisitos()[r.pk]
        self.assertEqual(e["resultado"], "desconocido")
        self.assertIn("Falta título/área o una equivalencia", e["explicacion"])  # pasó por la comparación determinista
        self.assertEqual(e["sugerencia"]["etiqueta"], ETIQUETA_SUGERENCIA)
        self.assertEqual(e["sugerencia"]["formacion"], "Ingeniería de Software")
        self.assertIn("No acredita el requisito", e["sugerencia"]["explicacion"])

    def test_bajo_el_umbral_no_hay_sugerencia(self, *_):
        r = self.regla("TITULO_AREA", {"titulos_admitidos": ["Medicina"]})
        self.assertNotIn("sugerencia", self.requisitos()[r.pk])
        self.assertGreater(UMBRAL_SUGERENCIA_TITULO, 0.0)

    def test_solo_en_titulo_area_desconocido_y_revisado(self, *_):
        coincide = self.regla("TITULO_AREA", {"areas_admitidas": [self.area.pk]}, obligatorio=False)
        sin_revisar = self.regla("TITULO_AREA", {"titulos_admitidos": ["Ingeniería en Sistemas"]}, validado=False, obligatorio=False)
        documento = self.regla("DOCUMENTO", {"descripcion": "Título de Ingeniería en Sistemas", "documento_exigido": "Copia"}, obligatorio=False)
        contrato_invalido = self.regla("TITULO_AREA", {"titulos_admitidos": ["Ingeniería en Sistemas"], "campo_extra": 1}, obligatorio=False)
        evaluaciones = self.requisitos()
        self.assertEqual(evaluaciones[coincide.pk]["resultado"], "cumple")
        self.assertIn("no está revisada", evaluaciones[contrato_invalido.pk]["explicacion"])
        for r in (coincide, sin_revisar, documento, contrato_invalido):
            self.assertNotIn("sugerencia", evaluaciones[r.pk])
        self.assertEqual(evaluaciones[documento.pk]["resultado"], "desconocido")  # los externos no cambian
        self.assertTrue(evaluaciones[documento.pk]["comprobacion_externa"])

    def test_sin_modelo_no_hay_sugerencia_ni_error(self, vector_conv, vector):
        r = self.regla("TITULO_AREA", {"titulos_admitidos": ["Ingeniería en Sistemas"]})
        vector.side_effect = ModeloNoDisponible("sin modelo")
        vector_conv.side_effect = ModeloNoDisponible("sin modelo")
        e = self.requisitos()[r.pk]
        self.assertEqual(e["resultado"], "desconocido")
        self.assertNotIn("sugerencia", e)

    def test_resultados_y_elegibilidad_identicos_con_y_sin_sugerencias(self, *_):
        self.regla("TITULO_AREA", {"titulos_admitidos": ["Ingeniería en Sistemas"]})
        self.regla("NACIONALIDAD", {"codigos_pais": ["EC"]})
        con = evaluar_convocatoria(self.user, self.conv, sugerencias=True)
        self.assertTrue(any("sugerencia" in e for o in con["opciones"] for e in o["requisitos"]))
        self.assertEqual(sin_sugerencias(con), sin_sugerencias(evaluar_convocatoria(self.user, self.conv)))

    def test_para_ti_no_usa_sugerencias_ni_cambia_su_orden(self, *_):
        self.regla("TITULO_AREA", {"titulos_admitidos": ["Ingeniería en Sistemas"]})
        antes = recomendar(self.user)
        with patch("convocatorias.comparacion.sugerir_titulos", side_effect=AssertionError("Para ti no pide sugerencias")):
            despues = recomendar(self.user)
        self.assertEqual([(r["convocatoria"]["id"], r["elegibilidad"]) for r in antes], [(r["convocatoria"]["id"], r["elegibilidad"]) for r in despues])


class NivelDeducidoFormacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        cls.user = get_user_model().objects.create_user(email="nivel@example.com", nombre="DEMO", password=None)
        cls.perfil = Perfil.objects.create(usuario=cls.user, nacionalidad=cls.ec)
        institucion = Institucion.objects.create(nombre="DEMO entidad", sector="publico", pais=cls.ec)
        cls.conv = Convocatoria.objects.create(institucion=institucion, titulo="DEMO nivel", revision="validada", clave_deduplicacion="nivel")
        OpcionEstudio.objects.create(convocatoria=cls.conv, nivel="grado", modalidad="virtual").paises.add(cls.ec)

    def regla(self, texto, valor=None):
        return Requisito.objects.create(convocatoria=self.conv, tipo_requisito=TipoRequisito.objects.get(codigo="FORMACION"),
            texto_original=texto, valor_estructurado=valor or {"nivel_minimo": "bachillerato", "estado_exigido": "concluidos", "titulo_obtenido": True},
            operador=CONTRATOS["FORMACION"][1], modo_comprobacion="dato_declarado", validado=True)

    def formacion(self, nivel, estado="concluidos", titulo=True):
        return Formacion.objects.create(perfil=self.perfil, nivel=nivel, carrera="DEMO", titulo_obtenido=titulo, estado_estudios=estado)

    def evaluacion(self, r):
        return {e["id"]: e for e in evaluar_convocatoria(self.user, self.conv)["opciones"][0]["requisitos"]}[r.pk]

    def test_solo_se_deduce_en_textos_inequivocos(self):
        bach = {"nivel_minimo": "bachillerato", "estado_exigido": "concluidos", "titulo_obtenido": True}
        grado = {"nivel_minimo": "grado", "estado_exigido": "concluidos", "titulo_obtenido": True}
        for texto in ("Contar con título de bachiller.", "Ser Bachiller", "Bachillerato concluido con título."):
            self.assertEqual(nivel_deducido(bach, texto), "bachillerato", texto)
        self.assertEqual(nivel_deducido(grado, "Título de tercer nivel concluido"), "grado")
        self.assertIsNone(nivel_deducido(grado, "Título de tercer nivel concluido (solo maestría)."))  # dos niveles
        self.assertIsNone(nivel_deducido(bach, "Bachiller o técnico superior"))
        self.assertIsNone(nivel_deducido(bach, "Haber concluido los estudios"))  # el texto no nombra el nivel
        self.assertIsNone(nivel_deducido({**bach, "niveles_admitidos": ["bachillerato"]}, "Ser Bachiller"))  # ya explícito
        self.assertIsNone(nivel_deducido({**bach, "nivel_minimo": "maestria"}, "Maestría"))  # fuera de los casos admitidos

    def test_coincidencia_exacta_cumple_y_lo_explica(self):
        r = self.regla("Ser Bachiller")
        self.formacion("bachillerato")
        e = self.evaluacion(r)
        self.assertEqual(e["resultado"], "cumple")
        self.assertIn("se dedujo del texto de la convocatoria", e["explicacion"])

    def test_nunca_infiere_no_cumple(self):
        r = self.regla("Ser Bachiller")
        for nivel, estado, titulo in (("grado", "concluidos", True), ("bachillerato", "en_curso", False)):
            with self.subTest(nivel=nivel, estado=estado):
                Formacion.objects.filter(perfil=self.perfil).delete()
                self.formacion(nivel, estado, titulo)
                e = self.evaluacion(r)
                self.assertEqual(e["resultado"], "desconocido")
                self.assertIn("falta determinar los niveles admitidos", e["explicacion"])

    def test_texto_ambiguo_sigue_pendiente(self):
        r = self.regla("Título de tercer nivel concluido (solo maestría).",
                       {"nivel_minimo": "grado", "estado_exigido": "concluidos", "titulo_obtenido": True})
        self.formacion("grado")
        self.assertEqual(self.evaluacion(r)["resultado"], "desconocido")


class NivelTituloDeducidoTests(TestCase):
    """TITULO_AREA que solo pide un nivel de título: deducción por reglas, nunca «no_cumple»."""

    @classmethod
    def setUpTestData(cls):
        cls.ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        cls.user = get_user_model().objects.create_user(email="nivel-titulo@example.com", nombre="DEMO", password=None)
        cls.perfil = Perfil.objects.create(usuario=cls.user, nacionalidad=cls.ec)
        institucion = Institucion.objects.create(nombre="DEMO entidad", sector="publico", pais=cls.ec)
        cls.conv = Convocatoria.objects.create(institucion=institucion, titulo="DEMO nivel de título", revision="validada", clave_deduplicacion="nivel-titulo")
        OpcionEstudio.objects.create(convocatoria=cls.conv, nivel="maestria", modalidad="virtual").paises.add(cls.ec)

    def regla(self, titulo, texto, codigo="TITULO_AREA", **kwargs):
        valor = {"titulos_admitidos": [titulo]} if codigo == "TITULO_AREA" else kwargs.pop("valor")
        return Requisito.objects.create(convocatoria=self.conv, tipo_requisito=TipoRequisito.objects.get(codigo=codigo),
            texto_original=texto, valor_estructurado=valor, operador=CONTRATOS[codigo][1],
            modo_comprobacion="entidad_oferente" if codigo in ("DOCUMENTO", "ACREDITACION", "OTRO") else "dato_declarado",
            validado=True, **kwargs)

    def formacion(self, nivel, estado="concluidos", titulo=True):
        return Formacion.objects.create(perfil=self.perfil, nivel=nivel, carrera="DEMO", titulo_obtenido=titulo, estado_estudios=estado)

    def evaluacion(self, r):
        return {e["id"]: e for e in evaluar_convocatoria(self.user, self.conv)["opciones"][0]["requisitos"]}[r.pk]

    def test_textos_inequivocos_y_con_condiciones_adicionales(self):
        def n(titulo, texto=None):
            return nivel_titulo_deducido({"titulos_admitidos": [titulo], "areas_admitidas": []}, texto or f"Contar con un {titulo}")
        self.assertEqual(n("título de tercer nivel de grado (licenciatura o ingeniería)"), "grado")
        self.assertEqual(n("título de bachiller."), "bachillerato")
        self.assertEqual(n("título de maestría"), "maestria")
        self.assertEqual(n("título de doctorado"), "doctorado")
        for titulo, texto in (
            ("título de cuarto nivel de grado, es decir maestría oficial.", None),  # cuarto nivel: no distingue
            ("título de tercer nivel de grado (licenciatura y/o ingeniería) que le habilite el acceso al master", None),
            ("título de tercer nivel de grado (licenciatura o ingeniería).", "Para el programa de maestría contar con un título de tercer nivel"),
            ("título de maestría", "Para el programa de doctorado contar con un título de maestría"),
            ("Título de tercer nivel hasta el 31 de julio de 2026 para aplicar a una maestría", None),
            ("título de tercer nivel de grado (licenciatura o equivalente).", None),
            ("título de maestría o ser profesor asociado", None),
            ("título de posgrado", None),
        ):
            with self.subTest(titulo=titulo):
                self.assertIsNone(n(titulo, texto))
        self.assertIsNone(nivel_titulo_deducido({"titulos_admitidos": ["título de bachiller", "título de grado"]}, "Bachiller o grado"))
        self.assertIsNone(nivel_titulo_deducido({"titulos_admitidos": ["título de bachiller"], "areas_admitidas": [1]}, "Título de bachiller"))
        self.assertIsNone(nivel_titulo_deducido({"titulos_admitidos": ["título de bachiller"]}, ""))

    def test_nivel_exacto_concluido_y_titulado_cumple(self):
        r = self.regla("título de tercer nivel de grado (licenciatura o ingeniería)", "Contar con un título de tercer nivel de grado (licenciatura o ingeniería)")
        self.formacion("grado")
        e = self.evaluacion(r)
        self.assertEqual(e["resultado"], "cumple")
        self.assertIn("se dedujo del texto de la convocatoria", e["explicacion"])
        self.assertNotIn("sugerencia", e)

    def test_nunca_no_cumple_ni_jerarquia(self):
        r = self.regla("título de tercer nivel de grado (licenciatura o ingeniería)", "Contar con un título de tercer nivel de grado (licenciatura o ingeniería)")
        # Una maestría no cuenta como «tercer nivel»; un grado en curso o sin título tampoco. Todo queda pendiente.
        for nivel, estado, titulo in (("maestria", "concluidos", True), ("grado", "en_curso", False), ("bachillerato", "concluidos", True)):
            with self.subTest(nivel=nivel, estado=estado):
                Formacion.objects.filter(perfil=self.perfil).delete()
                self.formacion(nivel, estado, titulo)
                e = self.evaluacion(r)
                self.assertEqual(e["resultado"], "desconocido")
                self.assertIn("Falta título/área o una equivalencia", e["explicacion"])

    def test_condicion_adicional_sigue_pendiente(self):
        r = self.regla("título de maestría o ser profesor asociado", "Contar con un título de maestría o ser profesor asociado")
        self.formacion("maestria")
        self.assertEqual(self.evaluacion(r)["resultado"], "desconocido")

    def test_tipos_externos_no_cambian(self):
        r = self.regla(None, "Título de tercer nivel registrado", codigo="DOCUMENTO",
                       valor={"descripcion": "Título de tercer nivel", "documento_exigido": "Copia del título"})
        self.formacion("grado")
        e = self.evaluacion(r)
        self.assertEqual(e["resultado"], "desconocido")
        self.assertTrue(e["comprobacion_externa"])
