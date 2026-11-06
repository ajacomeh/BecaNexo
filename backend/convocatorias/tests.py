from datetime import datetime, timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from perfiles.models import Pais, Area, Idioma
from . import models as m


class ConvocatoriasTests(TestCase):
    def test_documentacion_consulta_edicion_y_verificacion_externa(self):
        c = self.oferta()["id"]
        option = self.opcion(c)["id"]
        common = self.requisito(c, "DOCUMENTO", {"documento": "Título o certificado en emisión", "condiciones": "Cuando corresponda", "url_documento": "https://example.org/formulario"})
        specific = self.requisito(c, "ACREDITACION", {"certificados_admitidos": "Certificado de idioma", "url_documento": "https://example.org/certificado"}, opcion_estudio=option)
        self.assertEqual(common.status_code, 201, common.data)
        self.assertEqual(specific.status_code, 201, specific.data)
        common, specific = common.data, specific.data
        path = f"/api/gestion/convocatorias/{c}/requisitos/{common['id']}/"
        values = {"documento": "Título o certificado en emisión", "condiciones": "Registro cuando corresponda", "url_documento": "https://example.org/nuevo"}
        self.write(path, {"valor_estructurado": values}, method="patch", expected=200)
        self.assertEqual(self.client.get(path).data["valor_estructurado"], values)
        for url in ("javascript:alert(1)", "data:text/html,test", "https://user:pass@example.org/file"):
            self.write(path, {"valor_estructurado": {**values, "url_documento": url}}, method="patch", expected=400)
        self.assertEqual(self.client.patch(path, {"obligatorio": False}, format="json").status_code, 403)
        self.assertEqual(self.public.patch(path, {}, format="json").status_code, 403)
        m.Convocatoria.objects.filter(pk=c).update(revision="validada", activa=True)  # Solo fixture de pruebas.
        detail = self.public.get(f"/api/becas/{c}/").data
        self.assertEqual(len(detail["requisitos"]), 2)
        self.assertEqual(next(r for r in detail["requisitos"] if r["id"] == common["id"])["opcion_estudio"], None)
        self.assertEqual(next(r for r in detail["requisitos"] if r["id"] == specific["id"])["opcion_estudio"], option)
        self.client.force_login(self.student)
        token = self.client.get('/api/auth/csrf/').data['csrfToken']
        self.assertEqual(self.client.patch(path, {}, format="json", HTTP_X_CSRFTOKEN=token).status_code, 403)
        comparison = self.client.get(f"/api/becas/{c}/comparacion/").data
        for rule in comparison["opciones"][0]["requisitos"]:
            self.assertEqual(rule["resultado"], "desconocido")
            self.assertEqual(rule["estado_documental"], "pendiente_entidad_oferente")

    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user(email="admin-ofertas@example.com", password="Testing-Only-74!", nombre="Administrador sintético", rol="administrador")
        cls.student = get_user_model().objects.create_user(email="postulante-ofertas@example.com", password="Testing-Only-74!", nombre="Postulante sintético", is_staff=True)
        cls.ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        cls.es = Pais.objects.create(codigo="ES", nombre="España")
        cls.area = Area.objects.create(nombre="Área sintética")
        Idioma.objects.create(codigo="en", nombre="Inglés")
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        cls.institution = m.Institucion.objects.create(nombre="DEMO sintética", sector="publico", pais=cls.ec)

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.admin)
        self.token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        self.public = APIClient(enforce_csrf_checks=True)

    def write(self, path, data=None, method="post", expected=None):
        response = getattr(self.client, method)(path, data if data is not None else {}, format="json", HTTP_X_CSRFTOKEN=self.token)
        if expected: self.assertEqual(response.status_code, expected, response.data)
        return response

    def oferta(self, title="DEMONSTRACIÓN sintética"):
        return self.write("/api/gestion/convocatorias/", {"titulo": title, "institucion": self.institution.pk,
            "descripcion": "Datos sintéticos sin oferta real", "url_oficial": "https://example.org/demo", "areas": [self.area.pk]}, expected=201).data

    def opcion(self, c, **kwargs):
        return self.write(f"/api/gestion/convocatorias/{c}/opciones/", {"nivel": "maestria", "modalidad": "presencial", "paises": [self.ec.pk, self.es.pk], **kwargs}, expected=201).data

    def requisito(self, c, code, valor, **kwargs):
        external = code in ("ACREDITACION", "DOCUMENTO", "OTRO")
        return self.write(f"/api/gestion/convocatorias/{c}/requisitos/", {"tipo_requisito": m.TipoRequisito.objects.get(codigo=code).pk,
            "texto_original": "Condición sintética", "valor_estructurado": valor, "modo_comprobacion": "entidad_oferente" if external else "dato_declarado", "validado": True, **kwargs})

    def test_catalogos_idempotentes(self):
        ids = list(m.TipoRequisito.objects.values_list("pk", flat=True))
        call_command("cargar_catalogos_convocatorias", verbosity=0)
        self.assertEqual(ids, list(m.TipoRequisito.objects.values_list("pk", flat=True)))
        self.assertEqual(m.TipoBeca.objects.count(), 2)

    def test_permisos_y_csrf(self):
        self.assertFalse(self.admin.is_staff)
        self.assertEqual(self.client.post("/api/gestion/convocatorias/", {}, format="json").status_code, 403)
        self.assertEqual(self.public.get("/api/gestion/convocatorias/").status_code, 403)
        self.client.force_login(self.student)
        self.token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        self.write("/api/gestion/convocatorias/", {}, expected=403)
        self.assertEqual(self.client.get("/api/gestion/instituciones/").status_code, 403)

    def test_institucion_ec_y_auditoria(self):
        path = "/api/gestion/instituciones/"
        self.write(path, {"nombre": "Fuera de alcance", "sector": "publico", "pais": self.es.pk}, expected=400)
        response = self.write(path, {"nombre": "DEMO", "sector": "privado", "pais": self.ec.pk}, expected=201)
        pk = response.data["id"]
        self.write(f"{path}{pk}/", {"nombre": "DEMO corregida"}, "patch", 200)
        self.assertEqual(m.Evento.objects.filter(institucion_id=pk).count(), 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Evento.objects.create(actor=self.admin, accion="inválida", cambios={})

    def test_borrador_publicacion_pausa_edicion(self):
        c = self.oferta()["id"]
        path = f"/api/gestion/convocatorias/{c}/"
        self.assertEqual(self.public.get(f"/api/becas/{c}/").status_code, 404)
        self.assertEqual(self.public.get("/api/becas/").data["count"], 0)
        self.write(path + "publicar/", expected=400)
        self.opcion(c)
        self.write(path + "publicar/", expected=200)
        self.assertEqual(self.public.get(f"/api/becas/{c}/").status_code, 200)
        self.write(path, {"descripcion": "Actualizada"}, "patch", 200)
        self.assertEqual(self.public.get(f"/api/becas/{c}/").status_code, 404)
        self.write(path + "publicar/", expected=200)
        self.assertEqual(self.public.get(f"/api/becas/{c}/").data["descripcion"], "Actualizada")
        self.write(path + "pausar/", expected=200)
        self.assertEqual(self.public.get(f"/api/becas/{c}/").status_code, 404)
        self.assertEqual(m.Evento.objects.filter(convocatoria_id=c).count(), 6)
        self.write(path, {}, "delete", 405)

    def test_opciones_paises_unicidad(self):
        c = self.oferta()["id"]
        option = self.opcion(c)
        self.assertEqual(set(option["paises"]), {self.ec.pk, self.es.pk})
        path = f"/api/gestion/convocatorias/{c}/opciones/"
        self.write(path, {"nivel": "grado", "modalidad": "virtual", "paises": [self.ec.pk]*2}, expected=400)
        self.write(path, {"nivel": "maestria", "modalidad": "presencial"}, expected=400)
        self.write(path + str(option["id"]) + "/", {"cupos": 0}, "patch", 400)
        self.write(path + str(option["id"]) + "/", {"duracion_meses": -1}, "patch", 400)

    def test_beneficios_y_ambito(self):
        c = self.oferta()["id"]; other = self.oferta("Otra sintética")["id"]
        option = self.opcion(other)
        path = f"/api/gestion/convocatorias/{c}/beneficios/"
        for data in ({"porcentaje": 101}, {"porcentaje": -1}, {"monto": -1}, {"monto": 10}, {"opcion_estudio": option["id"]}):
            self.write(path, {"concepto": "Matrícula", **data}, expected=400)
        benefit = self.write(path, {"concepto": "Matrícula", "porcentaje": 80, "monto": 0, "moneda": "USD"}, expected=201).data
        self.assertEqual(benefit["porcentaje"], "80.00")
        self.write(path + str(benefit["id"]) + "/", method="delete", expected=204)

    def test_requisitos_contrato_todos_los_tipos(self):
        c = self.oferta()["id"]
        cases = {"NACIONALIDAD": {"codigos_pais": ["EC"]}, "FORMACION": {"nivel_minimo": "grado", "estado_exigido": "concluidos", "titulo_obtenido": True},
            "TITULO_AREA": {"areas_admitidas": [self.area.pk]}, "EDAD": {"maximo": 35}, "PROMEDIO": {"minimo": 8, "escala_min": 0, "escala_max": 10},
            "IDIOMA": {"codigo_idioma": "en", "nivel_minimo": "B2"}, "EXPERIENCIA": {"meses_minimos": 12}, "DEDICACION": {"valores_admitidos": ["completa"]},
            "TRASLADO": {"requerido": True, "destino": "ES"}, "RESIDENCIA": {"codigos_pais": ["EC"]},
            "ACREDITACION": {"certificados_admitidos": "Según bases"}, "DOCUMENTO": {"documento": "Carta"}, "OTRO": {"descripcion": "Consulta externa"}}
        for code, value in cases.items():
            with self.subTest(code=code):
                kwargs = {"fecha_referencia": "2026-11-30"} if code == "EDAD" else {}
                response = self.requisito(c, code, value, **kwargs)
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(self.requisito(c, code, {**value, "arbitrario": 1}, **kwargs).status_code, 400)

    def test_requisitos_invalidos_y_externos(self):
        c = self.oferta()["id"]
        for code, value in (("EDAD", {"minimo": 40, "maximo": 30}), ("PROMEDIO", {"minimo": 11, "escala_min": 0, "escala_max": 10}),
                ("FORMACION", {"nivel_minimo": "grado", "estado_exigido": "en_curso", "titulo_obtenido": True}),
                ("NACIONALIDAD", {"codigos_pais": ["ES"]}), ("EXPERIENCIA", {"meses_minimos": True}), ("IDIOMA", {"codigo_idioma": "en", "nivel_minimo": "Z9"})):
            self.assertEqual(self.requisito(c, code, value).status_code, 400)
        self.assertEqual(self.requisito(c, "ACREDITACION", {"certificados_admitidos": "Certificado"}, modo_comprobacion="dato_declarado").status_code, 400)
        other = self.oferta("Otra")["id"]; option = self.opcion(other)
        self.assertEqual(self.requisito(c, "EDAD", {"maximo": 35}, fecha_referencia="2026-11-30", opcion_estudio=option["id"]).status_code, 400)

    def test_publicacion_revision_y_superposicion(self):
        c = self.oferta()["id"]; option = self.opcion(c)
        req = self.requisito(c, "IDIOMA", {"codigo_idioma": "en", "nivel_minimo": "B2"}, validado=False).data
        base = f"/api/gestion/convocatorias/{c}/"
        self.write(base + "publicar/", expected=400)
        self.write(base + f"requisitos/{req['id']}/", {"validado": True}, "patch", 200)
        self.write(base + "publicar/", expected=200)
        self.write(base + "beneficios/", {"concepto": "Matrícula", "porcentaje": 80}, expected=201)
        self.write(base + "beneficios/", {"concepto": "Matrícula", "porcentaje": 20, "opcion_estudio": option["id"]}, expected=201)
        self.write(base + "publicar/", expected=400)

    def test_fechas_y_limite_cierre(self):
        c = self.oferta()["id"]; self.opcion(c)
        base = f"/api/gestion/convocatorias/{c}/"
        self.write(base, {"apertura": "2026-12-01T10:00:00-05:00", "cierre": "2026-11-01T10:00:00-05:00"}, "patch", 400)
        self.write(base, {"cierre": "2026-11-30T23:59:00-05:00"}, "patch", 200)
        self.write(base + "publicar/", expected=200)
        instant = m.Convocatoria.objects.get(pk=c).cierre
        with patch("django.utils.timezone.now", return_value=instant - timedelta(microseconds=1)):
            self.assertEqual(self.public.get(f"/api/becas/{c}/").data["estado"], "abierta")
        with patch("django.utils.timezone.now", return_value=instant):
            self.assertEqual(self.public.get(f"/api/becas/{c}/").data["estado"], "cerrada")
            self.assertEqual(self.public.get("/api/becas/?estado=abierta").data["count"], 0)

    def test_cierre_por_dia_sin_hora_y_filtros(self):
        c = self.oferta()["id"]
        self.opcion(c)
        path = f"/api/gestion/convocatorias/{c}/"
        self.write(path, {"cierre_dia": "2026-11-06"}, "patch", 400)
        self.write(path, {"cierre_dia": "2026-11-06", "cierre_original": "6 de noviembre de 2026"}, "patch", 200)
        self.write(path, {"cierre": "2026-11-06T23:59:00-05:00"}, "patch", 400)
        self.write(path + "publicar/", expected=200)
        self.assertIsNone(m.Convocatoria.objects.get(pk=c).cierre)
        cases = (("2026-11-05T12:00:00-05:00", "abierta"),
                 ("2026-11-06T08:00:00-05:00", "cierre_hoy"),
                 ("2026-11-06T22:00:00-05:00", "cierre_hoy"),
                 ("2026-11-07T00:01:00-05:00", "cerrada"))
        for moment, expected in cases:
            with self.subTest(moment=moment), patch("django.utils.timezone.now", return_value=datetime.fromisoformat(moment)):
                self.assertEqual(self.public.get(f"/api/becas/{c}/").data["estado"], expected)
                self.assertEqual(self.public.get(f"/api/becas/?estado={expected}").data["count"], 1)
                self.assertEqual(self.public.get("/api/becas/?estado=sin_fecha").data["count"], 0)
        m.Convocatoria.objects.filter(pk=c).update(apertura=datetime.fromisoformat("2026-11-06T12:00:00-05:00"))
        with patch("django.utils.timezone.now", return_value=datetime.fromisoformat("2026-11-06T08:00:00-05:00")):
            self.assertEqual(self.public.get(f"/api/becas/{c}/").data["estado"], "proxima")
            self.assertEqual(self.public.get("/api/becas/?estado=proxima").data["count"], 1)
            self.assertEqual(self.public.get("/api/becas/?estado=cierre_hoy").data["count"], 0)
        self.assertEqual(self.public.get("/api/becas/?orden=cierre").status_code, 200)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Convocatoria.objects.filter(pk=c).update(cierre=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Convocatoria.objects.filter(pk=c).update(cierre_original=None)

    def test_tope_separado_y_moneda_no_confirmada(self):
        c = self.oferta()["id"]
        path = f"/api/gestion/convocatorias/{c}/beneficios/"
        for invalid in ({"tope_monto": -1, "tope_original": "$3000"},
                        {"tope_monto": 3000},
                        {"tope_monto": 3000, "tope_original": "$3000", "tope_moneda": "usd"},
                        {"tope_original": "$3000", "tope_moneda": "USD"}):
            self.write(path, {"concepto": "Matrícula", **invalid}, expected=400)
        row = self.write(path, {"concepto": "Matrícula", "porcentaje": 100,
            "tope_original": "$3000", "tope_monto": 3000}, expected=201).data
        self.assertIsNone(row["monto"])
        self.assertIsNone(row["tope_moneda"])
        self.assertEqual(row["tope_original"], "$3000")
        self.opcion(c)
        self.write(f"/api/gestion/convocatorias/{c}/publicar/", expected=200)
        public = self.public.get(f"/api/becas/{c}/").data["beneficios"][0]
        self.assertEqual(public["tope_monto"], "3000.00")
        self.assertIsNone(public["tope_moneda"])
        self.assertEqual(public["tope_original"], "$3000")
        self.assertEqual(self.client.patch(path + str(row["id"]) + "/", {"tope_moneda": "USD"}, format="json").status_code, 403)
        self.write(path + str(row["id"]) + "/", {"tope_moneda": "USD"}, "patch", 200)
        self.assertEqual(m.Beneficio.objects.get(pk=row["id"]).tope_original, "$3000")
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Beneficio.objects.filter(pk=row["id"]).update(tope_original=None)

    def test_filtros_misma_opcion_y_paginacion(self):
        c = self.oferta()["id"]
        self.opcion(c, paises=[self.es.pk])
        self.opcion(c, nivel="grado", modalidad="virtual", paises=[self.ec.pk])
        self.write(f"/api/gestion/convocatorias/{c}/publicar/", expected=200)
        self.assertEqual(self.public.get("/api/becas/?nivel=maestria&destino=EC").data["count"], 0)
        self.assertEqual(self.public.get("/api/becas/?nivel=maestria&destino=ES&modalidad=presencial").data["count"], 1)
        self.assertEqual(self.public.get("/api/becas/?page_size=1&page=2").data["results"], [])
        for query in ("page_size=51", "page=0", "orden=password", "estado=borrador", "nivel=x", "destino=ZZ", "q=a&q=b", "arbitrario=1"):
            self.assertEqual(self.public.get("/api/becas/?" + query).status_code, 400)

    def test_campos_urls_metodos_y_atomicidad(self):
        c = self.oferta()["id"]; base = f"/api/gestion/convocatorias/{c}/"
        initial = m.Convocatoria.objects.get(pk=c).version
        for data in ({"revision": "validada"}, {"activa": True}, {"actor": self.admin.pk}, {"url_oficial": "javascript:alert(1)"}, {"url_oficial": "https://user:secret@example.com"}):
            self.write(base, data, "patch", 400)
        self.assertEqual(m.Convocatoria.objects.get(pk=c).version, initial)
        self.write(base, expected=405)
        self.write("/api/gestion/convocatorias/", {}, "patch", 405)
        self.assertEqual(self.public.post("/api/becas/", {}).status_code, 403)
        self.assertEqual(self.public.get(base + "auditoria/").status_code, 403)

    def test_cambio_oferente_retira_publicacion(self):
        c = self.oferta()["id"]; self.opcion(c)
        self.write(f"/api/gestion/convocatorias/{c}/publicar/", expected=200)
        self.write(f"/api/gestion/instituciones/{self.institution.pk}/", {"nombre": "DEMO modificada"}, "patch", 200)
        self.assertEqual(self.public.get(f"/api/becas/{c}/").status_code, 404)

    def test_csrf_en_todas_las_escrituras(self):
        c = self.oferta()["id"]; option = self.opcion(c)
        base = f"/api/gestion/convocatorias/{c}/"
        for method, path in (("patch", base), ("post", base + "publicar/"), ("post", base + "pausar/"),
                ("post", base + "opciones/"), ("patch", base + f"opciones/{option['id']}/"),
                ("post", base + "beneficios/"), ("post", base + "requisitos/"),
                ("post", "/api/gestion/instituciones/"), ("patch", f"/api/gestion/instituciones/{self.institution.pk}/")):
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(path, {}, format="json").status_code, 403)
                self.assertEqual(getattr(self.client, method)(path, {}, format="json", HTTP_X_CSRFTOKEN="invalid").status_code, 403)

    def test_restricciones_postgresql_y_auditoria_atomica(self):
        c = self.oferta()["id"]; option = self.opcion(c)
        for data in ({"porcentaje": -1}, {"porcentaje": 101}, {"monto": -1}, {"monto": 1, "moneda": None}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                m.Beneficio.objects.create(convocatoria_id=c, concepto="Sintético", **data)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.OpcionPais.objects.create(opcion_estudio_id=option["id"], pais=self.ec)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Evento.objects.create(actor=self.admin, convocatoria_id=c, institucion=self.institution, accion="inválida", cambios={})
        before = m.Convocatoria.objects.get(pk=c).version
        count = m.Evento.objects.count()
        with patch("convocatorias.api.audit", side_effect=RuntimeError("Fallo simulado")):
            with self.assertRaises(RuntimeError):
                self.write(f"/api/gestion/convocatorias/{c}/", {"descripcion": "No debe persistir"}, "patch")
        self.assertEqual(m.Convocatoria.objects.get(pk=c).version, before)
        self.assertEqual(m.Evento.objects.count(), count)

    def test_reglas_duplicadas_y_opciones_inactivas(self):
        c = self.oferta()["id"]; option = self.opcion(c)
        self.requisito(c, "EDAD", {"maximo": 30}, fecha_referencia="2026-11-30")
        self.requisito(c, "EDAD", {"minimo": 40}, fecha_referencia="2026-11-30", opcion_estudio=option["id"])
        self.write(f"/api/gestion/convocatorias/{c}/publicar/", expected=400)
        other = self.oferta("Otra publicada")["id"]
        self.opcion(other)
        hidden = self.opcion(other, nivel="grado", modalidad="virtual", activa=False)
        self.write(f"/api/gestion/convocatorias/{other}/publicar/", expected=200)
        response = self.public.get(f"/api/becas/{other}/")
        self.assertNotIn(hidden["id"], [x["id"] for x in response.data["opciones"]])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn("password", str(response.data))
