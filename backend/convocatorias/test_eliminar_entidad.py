"""Eliminación de entidades oferentes: bloqueo por convocatorias públicas, borradores desvinculados y auditoría.

Escribe solo en la base de pruebas aislada.
"""
from datetime import timedelta

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from . import models as m
from . import tests as base
from .services import publicas

ROOT = "/api/gestion/instituciones/"
BLOQUEO = "No se puede eliminar: la entidad tiene {} en el catálogo público. Despublica o reasigna esas convocatorias antes."


class EliminarEntidadTests(TestCase):
    setUp = base.ConvocatoriasTests.setUp
    write = base.ConvocatoriasTests.write
    opcion = base.ConvocatoriasTests.opcion

    @classmethod
    def setUpTestData(cls):
        base.ConvocatoriasTests.setUpTestData.__func__(cls)

    def entidad(self, nombre="Entidad sintética a eliminar"):
        data = self.write(ROOT, {"nombre": nombre, "sector": "privado", "pais": self.ec.pk}, expected=201).data
        return m.Institucion.objects.get(pk=data["id"])

    def oferta(self, entidad, titulo="Convocatoria sintética", publicar=False, **campos):
        pk = self.write("/api/gestion/convocatorias/", {"titulo": titulo, "institucion": entidad.pk, "descripcion": "Datos sintéticos",
                                                         "url_oficial": "https://example.org/demo", "areas": [self.area.pk]}, expected=201).data["id"]
        if campos:
            self.write(f"/api/gestion/convocatorias/{pk}/", campos, "patch", 200)
        if publicar:
            self.opcion(pk)
            self.write(f"/api/gestion/convocatorias/{pk}/publicar/", expected=200)
        return m.Convocatoria.objects.get(pk=pk)

    def eliminar(self, entidad, expected):
        return self.write(f"{ROOT}{entidad.pk}/", method="delete", expected=expected)

    def test_sin_convocatorias_se_elimina_y_queda_auditado_con_su_historial(self):
        entidad = self.entidad()
        creada = m.Evento.objects.get(institucion=entidad, accion="institucion_crear")
        respuesta = self.eliminar(entidad, 200)
        self.assertEqual(respuesta.data, {"borradores_desvinculados": 0})
        self.assertFalse(m.Institucion.objects.filter(pk=entidad.pk).exists())
        evento = m.Evento.objects.get(accion="eliminar_institucion")
        self.assertEqual(evento.actor, self.admin)
        self.assertEqual(evento.cambios["institucion_eliminada"]["nombre"], "Entidad sintética a eliminar")
        self.assertEqual(evento.cambios["borradores_desvinculados"], 0)
        # El historial de la entidad se conserva: pierde el vínculo y guarda la instantánea.
        creada.refresh_from_db()
        self.assertIsNone(creada.institucion_id)
        self.assertEqual(creada.cambios["institucion_eliminada"]["id"], entidad.pk)
        self.assertIn("despues", creada.cambios)
        self.assertEqual(self.write(f"{ROOT}{entidad.pk}/", method="delete").status_code, 404)

    def test_bloquea_con_convocatorias_vigente_proxima_cerrada_pausada_o_ya_publicada(self):
        ahora = timezone.now()
        casos = {
            "vigente": {"cierre": (ahora + timedelta(days=30)).isoformat()},
            "próxima": {"apertura": (ahora + timedelta(days=10)).isoformat(), "cierre": (ahora + timedelta(days=40)).isoformat()},
            "cerrada": {"cierre_dia": (timezone.localdate() - timedelta(days=1)).isoformat(), "cierre_original": "Cierre sintético, sin hora"},
        }
        for nombre, campos in casos.items():
            with self.subTest(nombre):
                entidad = self.entidad(f"Entidad {nombre}")
                oferta = self.oferta(entidad, f"Oferta {nombre}", publicar=True, **campos)
                self.assertEqual(oferta.estado, {"vigente": "abierta", "próxima": "proxima", "cerrada": "cerrada"}[nombre])
                respuesta = self.eliminar(entidad, 409)
                self.assertEqual(respuesta.data["detail"], BLOQUEO.format("1 convocatoria"))
                self.assertTrue(m.Institucion.objects.filter(pk=entidad.pk).exists())
                oferta.refresh_from_db()
                self.assertEqual(oferta.institucion_id, entidad.pk)
        entidad = self.entidad("Entidad pausada")
        pausada = self.oferta(entidad, "Oferta pausada", publicar=True)
        self.write(f"/api/gestion/convocatorias/{pausada.pk}/pausar/", expected=200)
        pausada.refresh_from_db()
        self.assertEqual(pausada.estado, "pausada")
        # Una ya publicada que volvió a revisión pendiente (p. ej. por editarla) también cuenta.
        editada = self.oferta(entidad, "Oferta publicada y editada", publicar=True)
        self.write(f"/api/gestion/convocatorias/{editada.pk}/", {"titulo": "Oferta editada"}, "patch", 200)
        editada.refresh_from_db()
        self.assertEqual(editada.revision, "pendiente")
        self.oferta(entidad, "Borrador privado")
        respuesta = self.eliminar(entidad, 409)
        self.assertEqual(respuesta.data["detail"], BLOQUEO.format("2 convocatorias"))
        self.assertEqual(respuesta.data["convocatorias_publicas"], 2)
        titulos = ["Oferta editada", "Oferta pausada"]
        self.assertEqual([c["titulo"] for c in respuesta.data["muestra_publicas"]], titulos)
        detalle = self.client.get(f"{ROOT}{entidad.pk}/").data
        self.assertEqual((detalle["convocatorias_publicas"], detalle["borradores_privados"]), (2, 1))
        self.assertEqual([c["titulo"] for c in detalle["muestra_publicas"]], titulos)
        self.assertEqual(m.Convocatoria.objects.filter(institucion=entidad).count(), 3)  # nada se desvinculó
        self.assertFalse(m.Evento.objects.filter(accion="eliminar_institucion").exists())

    def test_con_solo_borradores_los_desvincula_como_oferente_por_confirmar(self):
        entidad = self.entidad("Entidad con borradores")
        borrador = self.oferta(entidad, "Borrador uno")
        otro = self.oferta(entidad, "Borrador dos")
        version = borrador.version
        respuesta = self.eliminar(entidad, 200)
        self.assertEqual(respuesta.data, {"borradores_desvinculados": 2})
        for oferta in (borrador, otro):
            oferta.refresh_from_db()
            self.assertIsNone(oferta.institucion_id)
            self.assertEqual(oferta.revision, "pendiente")
        self.assertGreater(borrador.version, version)
        self.assertEqual(m.Evento.objects.get(accion="eliminar_institucion").cambios["borradores_desvinculados"], 2)
        marca = m.Evento.objects.get(convocatoria=borrador, accion="oferente_eliminado")
        self.assertEqual(marca.cambios["entidad_eliminada"]["nombre"], "Entidad con borradores")
        detalle = self.client.get(f"/api/gestion/convocatorias/{borrador.pk}/").data
        self.assertIsNone(detalle["institucion"])
        self.assertEqual(detalle["oferente_externo"], {"no_ecuatoriano": False, "nombre": None})  # «Oferente por confirmar»
        self.assertEqual(detalle["aviso_oferente"], "Esta beca no tiene una entidad oferente ecuatoriana asignada")

    def test_publicar_un_borrador_desvinculado_exige_la_confirmacion(self):
        entidad = self.entidad("Entidad que se elimina")
        borrador = self.oferta(entidad, "Borrador por publicar")
        self.opcion(borrador.pk)
        self.eliminar(entidad, 200)
        sin = self.write(f"/api/gestion/convocatorias/{borrador.pk}/publicar/", expected=400)
        self.assertTrue(sin.data["requiere_confirmacion_oferente"])
        self.assertFalse(publicas().filter(pk=borrador.pk).exists())
        self.write(f"/api/gestion/convocatorias/{borrador.pk}/publicar/", {"confirmar_oferente_no_ecuatoriano": True}, expected=200)
        self.assertTrue(publicas().filter(pk=borrador.pk).exists())
        evento = m.Evento.objects.filter(convocatoria=borrador, accion="confirmar_publicacion").get()
        self.assertTrue(evento.cambios["confirmacion_sin_entidad"])

    def test_solo_administradores_pueden_eliminar(self):
        entidad = self.entidad("Entidad protegida")
        for usuario in (None, self.student):
            cliente = APIClient(enforce_csrf_checks=True)
            if usuario:
                cliente.force_login(usuario)
            token = cliente.get("/api/auth/csrf/").data["csrfToken"]
            self.assertEqual(cliente.delete(f"{ROOT}{entidad.pk}/", HTTP_X_CSRFTOKEN=token).status_code, 403)
        sin_csrf = APIClient(enforce_csrf_checks=True)
        sin_csrf.force_login(self.admin)
        self.assertEqual(sin_csrf.delete(f"{ROOT}{entidad.pk}/").status_code, 403)
        self.assertEqual(self.write(ROOT, method="delete").status_code, 405)
        self.assertTrue(m.Institucion.objects.filter(pk=entidad.pk).exists())

    def test_la_lista_trae_contadores_correctos_sin_consultas_n_mas_1(self):
        entidad = self.entidad("Entidad con contadores")
        self.oferta(entidad, "Pública", publicar=True)
        self.oferta(entidad, "Borrador A")
        self.oferta(entidad, "Borrador B")
        vacia = self.entidad("Entidad sin convocatorias")
        with CaptureQueriesContext(connection) as consultas:
            filas = {r["id"]: r for r in self.client.get(ROOT, {"page_size": 50}).data["results"]}
        self.assertEqual((filas[entidad.pk]["convocatorias_publicas"], filas[entidad.pk]["borradores_privados"]), (1, 2))
        self.assertEqual((filas[vacia.pk]["convocatorias_publicas"], filas[vacia.pk]["borradores_privados"]), (0, 0))
        self.assertLessEqual(len(consultas), 6)
