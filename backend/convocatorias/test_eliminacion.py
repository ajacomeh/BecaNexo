"""Eliminación de requisitos y opciones de estudio desde el editor de convocatorias. Base aislada."""
from django.test import TestCase
from rest_framework.test import APIClient

from . import models as m
from . import tests as base


class EliminacionTests(TestCase):
    setUp = base.ConvocatoriasTests.setUp
    write = base.ConvocatoriasTests.write
    oferta = base.ConvocatoriasTests.oferta
    opcion = base.ConvocatoriasTests.opcion
    requisito = base.ConvocatoriasTests.requisito

    @classmethod
    def setUpTestData(cls):
        base.ConvocatoriasTests.setUpTestData.__func__(cls)

    def base(self, c):
        return f"/api/gestion/convocatorias/{c}/"

    def ultimo_evento(self, c, accion):
        return m.Evento.objects.filter(convocatoria_id=c, accion=accion).order_by("-id").first()

    def test_eliminar_requisito_audita_con_instantanea_y_actor_y_es_idempotente(self):
        c = self.oferta()["id"]
        req = self.requisito(c, "EDAD", {"maximo": 35}, fecha_referencia="2026-11-30").data
        self.write(self.base(c) + f"requisitos/{req['id']}/", method="delete", expected=204)
        self.assertFalse(m.Requisito.objects.filter(pk=req["id"]).exists())
        evento = self.ultimo_evento(c, "requisitos_eliminar")
        self.assertEqual(evento.actor_id, self.admin.pk)
        self.assertIn(req["id"], [r["id"] for r in evento.cambios["antes"]["requisitos"]])
        self.assertNotIn(req["id"], [r["id"] for r in evento.cambios["despues"]["requisitos"]])
        eventos = m.Evento.objects.filter(convocatoria_id=c).count()
        self.write(self.base(c) + f"requisitos/{req['id']}/", method="delete", expected=204)
        self.assertEqual(m.Evento.objects.filter(convocatoria_id=c).count(), eventos, "repetir no vuelve a auditar")
        self.write(self.base(c) + "requisitos/999999/", method="delete", expected=404)

    def test_eliminar_opcion_arrastra_sus_requisitos_propios_en_la_misma_transaccion(self):
        c = self.oferta()["id"]
        keep = self.opcion(c, programa="Se conserva")
        option = self.opcion(c, programa="Se elimina")
        propio = self.requisito(c, "EDAD", {"maximo": 30}, fecha_referencia="2026-11-30", opcion_estudio=option["id"]).data
        destino = self.requisito(c, "TRASLADO", {"requerido": True, "destino": "ES"}, opcion_estudio=option["id"], destino=self.es.pk).data
        comun = self.requisito(c, "EDAD", {"maximo": 40}, fecha_referencia="2026-11-30").data
        self.write(self.base(c) + f"opciones/{option['id']}/", method="delete", expected=204)
        self.assertFalse(m.OpcionEstudio.objects.filter(pk=option["id"]).exists())
        self.assertFalse(m.Requisito.objects.filter(pk__in=[propio["id"], destino["id"]]).exists())
        self.assertTrue(m.Requisito.objects.filter(pk=comun["id"]).exists())
        self.assertTrue(m.OpcionEstudio.objects.filter(pk=keep["id"]).exists())
        self.assertFalse(m.OpcionEstudio.paises.through.objects.filter(opcion_estudio_id=option["id"]).exists())
        evento = self.ultimo_evento(c, "opciones_eliminar")
        self.assertEqual(evento.actor_id, self.admin.pk)
        self.assertEqual({r["id"] for r in evento.cambios["antes"]["requisitos"]} - {r["id"] for r in evento.cambios["despues"]["requisitos"]},
                         {propio["id"], destino["id"]})
        # El requisito eliminado junto con su opción también responde de forma idempotente.
        self.write(self.base(c) + f"requisitos/{propio['id']}/", method="delete", expected=204)

    def test_opcion_con_beneficios_propios_se_rechaza_sin_eliminar_nada(self):
        c = self.oferta()["id"]
        option = self.opcion(c)
        self.write(self.base(c) + "beneficios/", {"concepto": "Matrícula", "porcentaje": 50, "opcion_estudio": option["id"]}, expected=201)
        response = self.write(self.base(c) + f"opciones/{option['id']}/", method="delete", expected=400)
        self.assertIn("beneficios propios", str(response.data))
        self.assertTrue(m.OpcionEstudio.objects.filter(pk=option["id"]).exists())
        self.assertFalse(m.Evento.objects.filter(convocatoria_id=c, accion="opciones_eliminar").exists())

    def test_publicada_rechaza_eliminar_la_ultima_opcion_activa_y_lo_demas_vuelve_a_revision(self):
        c = self.oferta()["id"]
        first = self.opcion(c)
        req = self.requisito(c, "EDAD", {"maximo": 35}, fecha_referencia="2026-11-30").data
        self.write(self.base(c) + "publicar/", expected=200)
        response = self.write(self.base(c) + f"opciones/{first['id']}/", method="delete", expected=400)
        self.assertIn("última opción activa", str(response.data))
        offer = m.Convocatoria.objects.get(pk=c)
        self.assertEqual((offer.revision, offer.activa), ("validada", True))
        # Eliminar un requisito de una convocatoria publicada la devuelve a revisión pendiente.
        self.write(self.base(c) + f"requisitos/{req['id']}/", method="delete", expected=204)
        offer.refresh_from_db()
        self.assertEqual(offer.revision, "pendiente")
        self.assertEqual(APIClient().get(f"/api/becas/{c}/").status_code, 404)
        self.write(self.base(c) + "publicar/", expected=200)
        # Con otra opción activa, eliminar una opción también devuelve a revisión, y se puede volver a publicar.
        second = self.opcion(c, modalidad="virtual")
        offer.refresh_from_db()
        self.write(self.base(c) + "publicar/", expected=200)
        self.write(self.base(c) + f"opciones/{first['id']}/", method="delete", expected=204)
        offer.refresh_from_db()
        self.assertEqual(offer.revision, "pendiente")
        self.write(self.base(c) + "publicar/", expected=200)
        self.assertEqual(list(m.Convocatoria.objects.get(pk=c).opciones.values_list("pk", flat=True)), [second["id"]])

    def test_desactivar_sigue_disponible_y_solo_administradores_con_csrf_pueden_eliminar(self):
        c = self.oferta()["id"]
        option = self.opcion(c)
        req = self.requisito(c, "EDAD", {"maximo": 35}, fecha_referencia="2026-11-30").data
        self.write(self.base(c) + f"requisitos/{req['id']}/", {"activo": False}, "patch", 200)
        self.write(self.base(c) + f"opciones/{option['id']}/", {"activa": False}, "patch", 200)
        self.assertFalse(m.Requisito.objects.get(pk=req["id"]).activo)
        self.assertFalse(m.OpcionEstudio.objects.get(pk=option["id"]).activa)
        student = APIClient(enforce_csrf_checks=True)
        student.force_login(self.student)
        token = student.get("/api/auth/csrf/").data["csrfToken"]
        self.assertEqual(student.delete(self.base(c) + f"requisitos/{req['id']}/", HTTP_X_CSRFTOKEN=token).status_code, 403)
        sin_csrf = APIClient(enforce_csrf_checks=True)
        sin_csrf.force_login(self.admin)
        self.assertEqual(sin_csrf.delete(self.base(c) + f"requisitos/{req['id']}/").status_code, 403)
        self.assertEqual(APIClient(enforce_csrf_checks=True).delete(self.base(c) + f"opciones/{option['id']}/").status_code, 403)
        self.assertTrue(m.Requisito.objects.filter(pk=req["id"]).exists())
        response = self.write(self.base(c) + f"requisitos/{req['id']}/", {"motivo": "x"}, "delete", 400)
        self.assertIn("no acepta campos", str(response.data))
