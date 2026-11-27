"""v1.1: aviso interno de «cierre próximo» para becas favoritas y su correo (misma regla general del correo).

Fechas relativas a «ahora»; correo en memoria; solo la base de pruebas aislada.
"""
import json
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from convocatorias.models import Convocatoria, Institucion, OpcionEstudio
from favoritos.models import Favorito
from perfiles.models import Pais
from .correo import procesar_pendientes
from .models import EntregaCorreo, Notificacion, PreferenciaCorreo
from .services import generar_avisos_cierre, texto_cierre

BASE_URL = "http://127.0.0.1:5173"


@override_settings(AVISOS_CIERRE_DIAS=3, AVISOS_CORREO_HABILITADOS=True, AVISOS_CORREO_MAX_POR_USUARIO=3,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", BECANEXO_PUBLIC_BASE_URL=BASE_URL)
class AvisoCierreProximoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ec = Pais.objects.create(codigo="EC", nombre="Ecuador")
        cls.entidad = Institucion.objects.create(nombre="Entidad ecuatoriana sintética", sector="publico", pais=cls.ec)
        users = get_user_model().objects
        cls.ana = users.create_user(email="ana-cierre@example.com", nombre="Ana", password=None)
        cls.beto = users.create_user(email="beto-cierre@example.com", nombre="Beto", password=None)
        cls.admin = users.create_user(email="admin-cierre@example.com", nombre="Admin", password=None, rol="administrador")
        cls.inactivo = users.create_user(email="inactivo-cierre@example.com", nombre="Inactivo", password=None, is_active=False)

    n = 0

    def beca(self, titulo="Beca por cerrar", dias=2, **campos):
        AvisoCierreProximoTests.n += 1
        datos = {"revision": "validada"}
        if dias is not None:
            datos["cierre"] = timezone.now() + timedelta(days=dias)
        if campos.get("cierre_dia"):
            datos["cierre_original"] = "Fecha de cierre según las bases, sin hora"
        datos.update(campos)
        c = Convocatoria.objects.create(institucion=self.entidad, titulo=titulo, descripcion="Solo pruebas",
                                        url_oficial="https://example.org/beca",
                                        clave_deduplicacion=f"cierre-{self.n}".ljust(64, "x"), **datos)
        OpcionEstudio.objects.create(convocatoria=c, nivel="maestria", modalidad="virtual")
        return c

    def favorita(self, usuario, convocatoria):
        return Favorito.objects.create(usuario=usuario, convocatoria=convocatoria)

    def avisos(self, **filtro):
        return Notificacion.objects.filter(tipo="cierre_proximo", **filtro)

    def test_genera_para_favorito_abierto_que_cierra_dentro_de_n_dias(self):
        beca = self.beca()
        self.favorita(self.ana, beca)
        resumen = generar_avisos_cierre()
        self.assertEqual((resumen["candidatos"], resumen["avisos"]), (1, 1))
        aviso = self.avisos().get()
        self.assertEqual((aviso.usuario_id, aviso.convocatoria_id, aviso.motivos), (self.ana.pk, beca.pk, ["cierre próximo de una beca favorita"]))
        local = timezone.localtime(beca.cierre)
        self.assertEqual(texto_cierre(beca), f"cierra el {local:%d/%m/%Y} a las {local:%H:%M} (hora de Ecuador)")

    def test_no_genera_fuera_de_la_regla(self):
        casos = {
            "cerrada": self.beca("Cerrada", dias=-1),
            "próxima": self.beca("Próxima", apertura=timezone.now() + timedelta(days=1)),
            "sin fecha": self.beca("Sin fecha", dias=None),
            "a más de N días": self.beca("Lejana", dias=10),
            "borrador": self.beca("Borrador", revision="pendiente"),
            "pausada": self.beca("Pausada", activa=False),
        }
        for beca in casos.values():
            self.favorita(self.ana, beca)
        self.assertEqual(generar_avisos_cierre()["avisos"], 0)
        self.assertFalse(self.avisos().exists())
        # Una favorita que deja de ser pública antes de avisar tampoco genera aviso.
        vigente = self.beca("Vigente que se despublica")
        self.favorita(self.ana, vigente)
        Convocatoria.objects.filter(pk=vigente.pk).update(revision="pendiente")
        self.assertEqual(generar_avisos_cierre()["avisos"], 0)

    def test_cierre_hoy_y_cierre_por_dia(self):
        hoy = self.beca("Cierra hoy", dias=None, cierre_dia=timezone.localdate())
        en_dos = self.beca("Cierra en dos días", dias=None, cierre_dia=timezone.localdate() + timedelta(days=2))
        self.favorita(self.ana, hoy)
        self.favorita(self.ana, en_dos)
        self.assertEqual(generar_avisos_cierre()["avisos"], 2)
        self.assertEqual(texto_cierre(hoy), "cierra hoy · hora no informada")
        self.assertEqual(texto_cierre(en_dos), f"cierra el {en_dos.cierre_dia:%d/%m/%Y} · hora no informada")

    def test_idempotente_aunque_se_quite_y_vuelva_a_agregar_el_favorito(self):
        beca = self.beca()
        favorito = self.favorita(self.ana, beca)
        self.assertEqual(generar_avisos_cierre()["avisos"], 1)
        self.assertEqual(generar_avisos_cierre(), {"candidatos": 0, "avisos": 0, "encolados": 0, "detalle": []})
        favorito.delete()
        self.favorita(self.ana, beca)
        self.assertEqual(generar_avisos_cierre()["avisos"], 0)
        self.assertEqual(self.avisos().count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notificacion.objects.create(usuario=self.ana, convocatoria=beca, tipo="cierre_proximo")

    def test_solo_postulantes_activos_y_usuario_sin_favoritos_no_recibe_nada(self):
        beca = self.beca()
        for usuario in (self.admin, self.inactivo):
            self.favorita(usuario, beca)
        self.assertEqual(generar_avisos_cierre()["avisos"], 0)
        self.favorita(self.ana, beca)
        generar_avisos_cierre()
        self.assertEqual(list(self.avisos().values_list("usuario_id", flat=True)), [self.ana.pk])
        self.assertFalse(Notificacion.objects.filter(usuario=self.beto).exists())

    def test_convive_con_el_aviso_de_publicacion(self):
        from notificaciones.services import avisar_publicacion
        beca = self.beca()
        publicacion = Notificacion.objects.create(usuario=self.ana, convocatoria=beca, motivos=["área de estudio declarada"])
        self.assertEqual(publicacion.tipo, "publicacion")  # los avisos existentes conservan su tipo
        self.favorita(self.ana, beca)
        self.assertEqual(generar_avisos_cierre()["avisos"], 1)
        self.assertEqual(set(Notificacion.objects.filter(usuario=self.ana, convocatoria=beca).values_list("tipo", flat=True)),
                         {"publicacion", "cierre_proximo"})
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notificacion.objects.create(usuario=self.ana, convocatoria=beca)  # la unicidad de publicación se mantiene
        # avisar_publicacion busca solo su tipo: no confunde el aviso de cierre.
        self.assertEqual(avisar_publicacion(beca), 0)

    def test_correo_solo_con_el_correo_activado_y_con_tope(self):
        PreferenciaCorreo.objects.create(usuario=self.ana, habilitada=True, actualizada_en=timezone.now() - timedelta(days=1))
        becas = [self.beca(f"Favorita {i}") for i in range(4)]
        for beca in becas:
            self.favorita(self.ana, beca)
            self.favorita(self.beto, beca)  # Beto no activó el correo
        resumen = generar_avisos_cierre()
        self.assertEqual((resumen["avisos"], resumen["encolados"]), (8, 4))
        self.assertEqual(set(EntregaCorreo.objects.values_list("notificacion__usuario_id", flat=True)), {self.ana.pk})
        self.assertEqual(procesar_pendientes(limite=10)["enviados"], 3)  # tope por usuario y corrida
        self.assertEqual(procesar_pendientes(limite=10)["enviados"], 1)
        self.assertEqual(procesar_pendientes(limite=10)["enviados"], 0)
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(generar_avisos_cierre()["encolados"], 0)  # un aviso, un correo

    def test_contenido_del_correo_de_cierre(self):
        PreferenciaCorreo.objects.create(usuario=self.ana, habilitada=True, actualizada_en=timezone.now() - timedelta(days=1))
        beca = self.beca("Beca favorita sintética", dias=None, cierre_dia=timezone.localdate())
        self.favorita(self.ana, beca)
        generar_avisos_cierre()
        self.assertEqual(procesar_pendientes(limite=5)["enviados"], 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.ana.email])
        self.assertEqual(message.subject, "BecaNexo · Cierre próximo: Beca favorita sintética")
        self.assertIn("Esta beca de tus favoritas cierra hoy · hora no informada.", message.body)
        self.assertIn(f"{BASE_URL}/becas/{beca.pk}", message.body)
        self.assertIn(f"{BASE_URL}/notificaciones", message.body)
        self.assertIn("Para dejar de recibirlos, desactiva", message.body)
        self.assertNotIn("Coincidencia", message.body)

    def test_correo_omitido_si_la_beca_ya_cerro_al_enviar(self):
        PreferenciaCorreo.objects.create(usuario=self.ana, habilitada=True, actualizada_en=timezone.now() - timedelta(days=1))
        beca = self.beca()
        self.favorita(self.ana, beca)
        generar_avisos_cierre()
        Convocatoria.objects.filter(pk=beca.pk).update(cierre=timezone.now() - timedelta(minutes=1))
        self.assertEqual(procesar_pendientes(limite=5)["omitidos"], 1)
        self.assertEqual(EntregaCorreo.objects.get().codigo_error, "oferta_ya_cerrada")
        self.assertEqual(mail.outbox, [])
        self.assertTrue(self.avisos().exists())  # el aviso interno se conserva

    def test_comando_dry_run_no_escribe_y_resume(self):
        self.favorita(self.ana, self.beca())
        self.favorita(self.ana, self.beca("Lejana", dias=10))
        out = StringIO()
        call_command("generar_avisos_cierre", "--dry-run", stdout=out)
        lineas = out.getvalue().strip().splitlines()
        self.assertEqual(len([l for l in lineas if l.startswith("generaría:")]), 1)
        self.assertNotIn("@", out.getvalue())  # sin correos ni nombres
        self.assertEqual(json.loads(lineas[-1]), {"candidatos": 1, "avisos": 0, "encolados": 0, "simulacion": True, "dias": 3})
        self.assertFalse(self.avisos().exists())
        out = StringIO()
        call_command("generar_avisos_cierre", "--dias", "15", stdout=out)
        self.assertEqual(json.loads(out.getvalue().strip().splitlines()[-1]), {"candidatos": 2, "avisos": 2, "encolados": 0, "dias": 15})

    def test_api_de_avisos_con_el_tipo_nuevo(self):
        beca = self.beca("Favorita en la bandeja")
        Notificacion.objects.create(usuario=self.ana, convocatoria=self.beca("Publicada"), motivos=["área de estudio declarada"])
        self.favorita(self.ana, beca)
        generar_avisos_cierre()
        client = APIClient()
        client.force_login(self.ana)
        data = client.get("/api/notificaciones/").data
        self.assertEqual((data["count"], data["no_leidas"]), (2, 2))
        por_tipo = {item["tipo"]: item for item in data["results"]}
        self.assertEqual(por_tipo["cierre_proximo"]["cierre_texto"], texto_cierre(beca))
        self.assertIsNone(por_tipo["publicacion"]["cierre_texto"])
        token = client.get("/api/auth/csrf/").data["csrfToken"]
        client.post(f"/api/notificaciones/{por_tipo['cierre_proximo']['id']}/leer/", {}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(client.get("/api/notificaciones/").data["no_leidas"], 1)
