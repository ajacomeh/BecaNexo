from django.test import TestCase
from rest_framework.test import APIClient
from perfiles.models import Pais
from .models import Institucion, Convocatoria, OpcionEstudio, TipoRequisito, Requisito


class ConsultaAnonimaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        institution = Institucion.objects.create(nombre="Entidad sintética", sector="publico", pais=ec)
        cls.ids = {}
        for index, (name, revision, active) in enumerate((("Publicada", "validada", True), ("Borrador", "pendiente", True), ("Pausada", "validada", False))):
            c = Convocatoria.objects.create(institucion=institution, titulo=name, descripcion="Prueba", url_oficial="https://example.org/beca", clave_deduplicacion=str(index)*64, revision=revision, activa=active)
            cls.ids[name] = c.pk
        OpcionEstudio.objects.create(convocatoria_id=cls.ids["Publicada"], nivel="maestria", modalidad="virtual")
        tipo = TipoRequisito.objects.create(codigo="OTRO", nombre="Condición", esquema_valor={})
        Requisito.objects.create(convocatoria_id=cls.ids["Publicada"], tipo_requisito=tipo, texto_original="Condición pública", modo_comprobacion="entidad_oferente", validado=True)

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def test_lista_filtros_paginacion_y_detalle_anonimos(self):
        result = self.client.get("/api/becas/?nivel=maestria&modalidad=virtual&page_size=1")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["results"][0]["id"], self.ids["Publicada"])
        self.assertEqual(self.client.get("/api/becas/?page=2&page_size=1").data["results"], [])
        detail = self.client.get(f"/api/becas/{self.ids['Publicada']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["url_oficial"], "https://example.org/beca")
        for key in ("revision", "activa", "version", "clave_deduplicacion", "favorito_id", "eventos"):
            self.assertNotIn(key, detail.data)
        self.assertNotIn("activa", detail.data["opciones"][0])
        self.assertNotIn("validado", detail.data["requisitos"][0])
        self.assertNotIn("activo", detail.data["requisitos"][0])

    def test_borrador_y_pausada_no_se_exponen(self):
        result = self.client.get("/api/becas/").data
        self.assertEqual(result["count"], 1)
        for name in ("Borrador", "Pausada"):
            self.assertEqual(self.client.get(f"/api/becas/{self.ids[name]}/").status_code, 404)
            self.assertEqual(self.client.get("/api/becas/", {"q": name}).data["count"], 0)

    def test_perfiles_favoritos_y_gestion_siguen_protegidos(self):
        for path in ("/api/perfil/", "/api/perfil/preferencias/", "/api/favoritos/", "/api/gestion/convocatorias/"):
            self.assertEqual(self.client.get(path).status_code, 403)
        token = self.client.get("/api/auth/csrf/").data["csrfToken"]
        self.assertEqual(self.client.post("/api/favoritos/", {"convocatoria": self.ids["Publicada"]}, format="json", HTTP_X_CSRFTOKEN=token).status_code, 403)
