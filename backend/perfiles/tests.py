from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from usuarios.models import Usuario
from . import models as m
from .api import RECURSOS


class PerfilTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_catalogos", stdout=StringIO())
        cls.ec = m.Pais.objects.get(codigo="EC")
        cls.es = m.Pais.objects.get(codigo="ES")
        cls.idioma = m.Idioma.objects.get(codigo="en")
        cls.area = m.Area.objects.first()
        cls.user = Usuario.objects.create_user("perfil@example.com", "Prueba")
        cls.other = Usuario.objects.create_user("otro@example.com", "Otra prueba")
        cls.admin = Usuario.objects.create_user("admin-perfil@example.com", "Admin", rol="administrador")

    def setUp(self):
        self.client = self.client_for(self.user)

    def client_for(self, user):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        token = client.get("/api/auth/csrf/").json()["csrfToken"]
        client.credentials(HTTP_X_CSRFTOKEN=token)
        return client

    def perfil(self):
        response = self.client.patch("/api/perfil/", {"nacionalidad": self.ec.pk}, format="json")
        self.assertIn(response.status_code, (200, 201))
        return m.Perfil.objects.get(usuario=self.user)

    def payloads(self):
        return {
            "formaciones": {"nivel": "grado", "carrera": "Software", "estado_estudios": "en_curso", "titulo_obtenido": False},
            "experiencias": {"fecha_inicio": "2020-01-01", "actual": True},
            "idiomas": {"idioma": self.idioma.pk, "nivel": None},
            "areas": {"area": self.area.pk},
            "preferencias": {"nivel": "maestria", "modalidad": "virtual"},
            "destinos": {"pais": self.es.pk},
        }

    def test_creacion_progresiva_y_unicidad(self):
        self.assertEqual(self.client.get("/api/perfil/").json(), {"perfil": None})
        perfil = self.perfil()
        self.assertEqual(perfil.nacionalidad, self.ec)
        self.assertIsNone(perfil.residencia)
        self.assertIsNone(perfil.disponible_traslado)
        self.assertEqual(perfil.version, 1)
        response = self.client.patch("/api/perfil/", {"ciudad_residencia": "Quito"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(m.Perfil.objects.filter(usuario=self.user).count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Perfil.objects.create(usuario=self.user, nacionalidad=self.ec)

    def test_anonimo_y_administrador(self):
        for client in (APIClient(enforce_csrf_checks=True), self.client_for(self.admin)):
            for path in ("", *[f"{key}/" for key in RECURSOS]):
                self.assertEqual(client.get(f"/api/perfil/{path}").status_code, 403)
                self.assertEqual(client.post(f"/api/perfil/{path}", {}, format="json").status_code, 403)
            self.assertEqual(client.patch("/api/perfil/", {}, format="json").status_code, 403)
        admin_client = self.client_for(self.admin)
        self.assertEqual(admin_client.get("/api/perfil/catalogos/").status_code, 200)
        self.assertEqual(admin_client.post("/api/perfil/catalogos/", {}, format="json").status_code, 405)
        self.assertEqual(APIClient().get("/api/perfil/catalogos/").status_code, 403)

    def test_campos_propietario_y_administrativos_rechazados(self):
        self.perfil()
        for field in ("usuario_id", "usuario", "perfil_id", "rol", "nombre", "version", "actualizado_en", "is_staff"):
            response = self.client.patch("/api/perfil/", {field: 1}, format="json")
            self.assertEqual(response.status_code, 400)
        for recurso, payload in self.payloads().items():
            for field in ("perfil", "perfil_id", "usuario_id", "rol", "id"):
                response = self.client.post(f"/api/perfil/{recurso}/", {**payload, field: self.other.pk}, format="json")
                self.assertEqual(response.status_code, 400)
            created = self.client.post(f"/api/perfil/{recurso}/", payload, format="json")
            self.assertEqual(created.status_code, 201)
            response = self.client.delete(f"/api/perfil/{recurso}/{created.data['id']}/", {"usuario_id": self.other.pk}, format="json")
            self.assertEqual(response.status_code, 400)

    def test_separacion_completa_entre_postulantes(self):
        perfil = self.perfil()
        other = self.client_for(self.other)
        self.assertEqual(other.patch("/api/perfil/", {"nacionalidad": self.ec.pk}, format="json").status_code, 201)
        for recurso, payload in self.payloads().items():
            created = self.client.post(f"/api/perfil/{recurso}/", payload, format="json")
            self.assertEqual(created.status_code, 201, created.data)
            path = f"/api/perfil/{recurso}/{created.data['id']}/"
            self.assertEqual(other.get(f"/api/perfil/{recurso}/").json(), [])
            self.assertEqual(other.get(path).status_code, 404)
            self.assertEqual(other.patch(path, payload, format="json").status_code, 404)
            self.assertEqual(other.delete(path).status_code, 404)
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(m.Perfil.objects.get(usuario=self.other).version, 1)
        perfil.refresh_from_db()
        self.assertEqual(perfil.version, 7)

    def test_csrf_todas_las_escrituras(self):
        self.perfil()
        paths = []
        for recurso, payload in self.payloads().items():
            created = self.client.post(f"/api/perfil/{recurso}/", payload, format="json").json()
            paths.append((recurso, created['id']))
        self.client.credentials()
        self.assertEqual(self.client.patch("/api/perfil/", {}, format="json").status_code, 403)
        for recurso, pk in paths:
            self.assertEqual(self.client.post(f"/api/perfil/{recurso}/", {}, format="json").status_code, 403)
            self.assertEqual(self.client.patch(f"/api/perfil/{recurso}/{pk}/", {}, format="json").status_code, 403)
            self.assertEqual(self.client.delete(f"/api/perfil/{recurso}/{pk}/").status_code, 403)

    def test_nacionalidad_residencia_y_fecha(self):
        for data in ({}, {"nacionalidad": None}, {"nacionalidad": ""}):
            self.assertEqual(self.client.patch("/api/perfil/", data, format="json").status_code, 400)
        self.assertFalse(m.Perfil.objects.exists())
        self.assertEqual(self.client.patch("/api/perfil/", {"nacionalidad": self.es.pk}, format="json").status_code, 400)
        self.assertFalse(m.Perfil.objects.exists())
        response = self.client.patch("/api/perfil/", {"nacionalidad": self.ec.pk, "residencia": self.es.pk}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['perfil']['nacionalidad'], self.ec.pk)
        self.assertEqual(response.data['perfil']['residencia'], self.es.pk)
        for data in ({"nacionalidad": self.es.pk}, {"nacionalidad": None}):
            self.assertEqual(self.client.patch("/api/perfil/", data, format="json").status_code, 400)
        self.assertEqual(self.client.patch("/api/perfil/", {"ciudad_residencia": "Otra"}, format="json").status_code, 200)
        self.assertEqual(self.client.get("/api/perfil/").json()['perfil']['nacionalidad'], self.ec.pk)
        tomorrow = str(timezone.localdate() + timedelta(days=1))
        self.assertEqual(self.client.patch("/api/perfil/", {"fecha_nacimiento": tomorrow}, format="json").status_code, 400)

    def test_nacionalidad_sin_ecuador(self):
        self.ec.delete()
        self.assertEqual(self.client.patch("/api/perfil/", {}, format="json").status_code, 503)
        self.assertFalse(m.Perfil.objects.exists())

    def test_descripcion_opcional_propia(self):
        perfil = self.perfil()
        self.assertIsNone(perfil.descripcion)
        path = "/api/perfil/"
        for text in ("Intereses <b>académicos</b>", "x" * 1500, "Objetivos editados"):
            self.assertEqual(self.client.patch(path, {"descripcion": text}, format="json").status_code, 200)
            self.assertEqual(self.client.get(path).json()["perfil"]["descripcion"], text)
        self.assertEqual(self.client.patch(path, {"descripcion": "x" * 1501}, format="json").status_code, 400)
        self.assertEqual(self.client.get(path).json()["perfil"]["descripcion"], "Objetivos editados")
        other = self.client_for(self.other)
        self.assertIsNone(other.get(path).json()["perfil"])
        self.assertEqual(other.patch(path, {"usuario_id": self.user.pk, "descripcion": "Ajena"}, format="json").status_code, 400)
        self.assertEqual(other.patch(f"/api/perfil/{perfil.pk}/", {"descripcion": "Ajena"}, format="json").status_code, 404)
        anonymous = APIClient(enforce_csrf_checks=True)
        self.assertEqual(anonymous.get(path).status_code, 403)
        no_csrf = APIClient(enforce_csrf_checks=True)
        no_csrf.force_login(self.user)
        self.assertEqual(no_csrf.patch(path, {"descripcion": "Sin CSRF"}, format="json").status_code, 403)
        for empty in ("", "   ", None):
            self.assertEqual(self.client.patch(path, {"descripcion": empty}, format="json").status_code, 200)
            self.assertIsNone(self.client.get(path).json()["perfil"]["descripcion"])

    def test_desconocido_no_equivale_a_false_o_cero(self):
        perfil = self.perfil()
        self.client.patch("/api/perfil/", {"disponible_traslado": False, "disponible_extranjero": None, "ciudad_residencia": "   "}, format="json")
        perfil.refresh_from_db()
        self.assertIs(perfil.disponible_traslado, False)
        self.assertIsNone(perfil.disponible_extranjero)
        self.assertIsNone(perfil.ciudad_residencia)
        response = self.client.post("/api/perfil/formaciones/", self.payloads()['formaciones'], format="json")
        self.assertIsNone(response.data['promedio'])
        self.assertEqual(self.client.get("/api/perfil/experiencias/").json(), [])

    def test_validaciones_formacion_y_patch_parcial(self):
        self.perfil()
        data = self.payloads()['formaciones']
        invalid = [{"titulo_obtenido": True}, {"fecha_finalizacion": "2020-01-01"},
                   {"promedio": "8"}, {"promedio": "8", "escala_min": "10", "escala_max": "0"},
                   {"promedio": "11", "escala_min": "0", "escala_max": "10"}, {"nivel": "invalido"},
                   {"estado_estudios": "otro"}, {"carrera": " "}]
        for extra in invalid:
            with self.subTest(extra=extra):
                self.assertEqual(self.client.post("/api/perfil/formaciones/", {**data, **extra}, format="json").status_code, 400)
        response = self.client.post("/api/perfil/formaciones/", {**data, "estado_estudios": "concluidos", "titulo_obtenido": True,
            "promedio": "0", "escala_min": "0", "escala_max": "10", "fecha_finalizacion": "2021-01-01"}, format="json")
        self.assertEqual(response.status_code, 201)
        path = f"/api/perfil/formaciones/{response.data['id']}/"
        self.assertEqual(self.client.patch(path, {"estado_estudios": "en_curso"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(path, {"promedio": None, "escala_min": None, "escala_max": None}, format="json").status_code, 200)

    def test_validaciones_experiencia(self):
        self.perfil()
        data = self.payloads()['experiencias']
        for extra in [{"actual": False}, {"fecha_fin": "2020-02-01"}, {"fecha_inicio": "2999-01-01"},
                      {"actual": False, "fecha_fin": "2019-01-01"}, {"actual": False, "fecha_fin": "2999-01-01"}]:
            self.assertEqual(self.client.post("/api/perfil/experiencias/", {**data, **extra}, format="json").status_code, 400)
        response = self.client.post("/api/perfil/experiencias/", data, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.patch(f"/api/perfil/experiencias/{response.data['id']}/",
            {"actual": False, "fecha_fin": "2020-03-01"}, format="json").status_code, 200)
        path = f"/api/perfil/experiencias/{response.data['id']}/"
        # PATCH combina los campos recibidos con los ya guardados.
        self.assertEqual(self.client.patch(path, {"actual": True}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(path, {"fecha_fin": None}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(path, {"actual": True, "fecha_fin": None}, format="json").status_code, 200)
        stored = self.client.get(path).json()
        self.assertTrue(stored["actual"])
        self.assertIsNone(stored["fecha_fin"])
        self.assertEqual(self.client.patch(path, {"fecha_fin": "2020-03-01"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(path, {"actual": False}, format="json").status_code, 400)
        self.assertIsNone(self.client.get(path).json()["fecha_fin"])

    def test_idiomas_dominios_y_duplicados(self):
        self.perfil()
        for nivel in ("B3", "certificado", "nativo"):
            self.assertEqual(self.client.post("/api/perfil/idiomas/", {"idioma": self.idioma.pk, "nivel": nivel}, format="json").status_code, 400)
        for recurso in ("idiomas", "areas", "destinos", "preferencias"):
            data = self.payloads()[recurso]
            self.assertEqual(self.client.post(f"/api/perfil/{recurso}/", data, format="json").status_code, 201)
            before = m.Perfil.objects.get(usuario=self.user).version
            self.assertEqual(self.client.post(f"/api/perfil/{recurso}/", data, format="json").status_code, 400)
            self.assertEqual(m.Perfil.objects.get(usuario=self.user).version, before)
        self.assertEqual(self.client.post("/api/perfil/preferencias/", {"nivel": "grado", "modalidad": "cualquiera"}, format="json").status_code, 400)

    def test_version_en_todos_los_recursos_y_eliminacion(self):
        perfil = self.perfil()
        version = 1
        for recurso, payload in self.payloads().items():
            response = self.client.post(f"/api/perfil/{recurso}/", payload, format="json")
            self.assertEqual(response.status_code, 201)
            path = f"/api/perfil/{recurso}/{response.data['id']}/"
            version += 1
            self.assertEqual(m.Perfil.objects.get(pk=perfil.pk).version, version)
            self.assertEqual(self.client.patch(path, payload, format="json").status_code, 200)
            self.assertEqual(self.client.delete(path).status_code, 204)
            version += 2
            current = m.Perfil.objects.get(pk=perfil.pk)
            self.assertEqual(current.version, version)
            self.assertGreater(current.actualizado_en, perfil.actualizado_en)

    def test_rollback_de_cambio_relacion_y_version(self):
        perfil = self.perfil()
        with patch("perfiles.api.incrementar", side_effect=RuntimeError("fallo controlado de prueba")):
            with self.assertRaises(RuntimeError):
                self.client.post("/api/perfil/formaciones/", self.payloads()['formaciones'], format="json")
        self.assertFalse(m.Formacion.objects.exists())
        perfil.refresh_from_db()
        self.assertEqual(perfil.version, 1)

    def test_restricciones_postgresql(self):
        perfil = self.perfil()
        formacion = m.Formacion.objects.create(perfil=perfil, **self.payloads()['formaciones'])
        for values in ({"nivel": "otro"}, {"titulo_obtenido": True}, {"promedio": 5}, {"carrera": " "}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                m.Formacion.objects.filter(pk=formacion.pk).update(**values)
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.PerfilIdioma.objects.create(perfil=perfil, idioma=self.idioma, nivel="Z9")
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.Experiencia.objects.create(perfil=perfil, fecha_inicio="2020-01-01", actual=False)

    def test_catalogos_idempotentes(self):
        before = [list(model.objects.values_list("id", flat=True)) for model in (m.Pais, m.Idioma, m.Area)]
        call_command("cargar_catalogos", stdout=StringIO())
        after = [list(model.objects.values_list("id", flat=True)) for model in (m.Pais, m.Idioma, m.Area)]
        self.assertEqual(before, after)
        self.assertEqual([len(ids) for ids in after], [249, 12, 11])

    def test_perfil_requerido_y_respuestas_sin_datos_de_usuario(self):
        response = self.client.post("/api/perfil/formaciones/", self.payloads()['formaciones'], format="json")
        self.assertEqual(response.status_code, 409)
        self.perfil()
        data = self.client.get("/api/perfil/").json()['perfil']
        self.assertFalse(set(data) & {"usuario", "usuario_id", "password", "password_hash", "is_staff", "rol"})


class VersionConcurrenteTests(TransactionTestCase):
    def test_dos_escrituras_concurrentes_no_pierden_version(self):
        ec = m.Pais.objects.create(codigo="EC", nombre="Ecuador")
        user = Usuario.objects.create_user("concurrencia@example.com", "Prueba")
        perfil = m.Perfil.objects.create(usuario=user, nacionalidad=ec)
        def escribir(carrera):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(Usuario.objects.get(pk=user.pk))
                return client.post("/api/perfil/formaciones/", {"nivel": "grado", "carrera": carrera,
                    "estado_estudios": "en_curso", "titulo_obtenido": False}, format="json").status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(escribir, ["Primera", "Segunda"]))
        self.assertEqual(results, [201, 201])
        perfil.refresh_from_db()
        self.assertEqual(perfil.version, 3)
        self.assertEqual(perfil.formaciones.count(), 2)
