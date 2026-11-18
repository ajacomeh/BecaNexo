"""Despacha la cola de correo fuera de las solicitudes web, o prueba SMTP una vez."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from notificaciones.correo import procesar_pendientes


class Command(BaseCommand):
    help = "Envía avisos pendientes o un único mensaje sintético a una dirección controlada."

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=10)
        parser.add_argument("--solo-id", type=int)
        parser.add_argument("--confirmar-envios", action="store_true")
        parser.add_argument("--prueba-a")
        parser.add_argument("--confirmar-prueba", action="store_true")

    def handle(self, *args, **options):
        smtp = settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend"
        if not smtp or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            raise CommandError("Configura Gmail SMTP antes de entregar; el backend de consola no acredita envíos.")
        if options["prueba_a"]:
            if not options["confirmar_prueba"] or options["confirmar_envios"] or options["solo_id"]:
                raise CommandError("La prueba requiere --prueba-a y --confirmar-prueba, sin opciones de cola.")
            try:
                validate_email(options["prueba_a"])
            except ValidationError as exc:
                raise CommandError("Dirección de prueba inválida.") from exc
            message = EmailMessage("BecaNexo · Prueba única de correo",
                                   "Este mensaje confirma únicamente la configuración de Gmail SMTP. No representa una beca ni una recomendación.",
                                   settings.DEFAULT_FROM_EMAIL, [options["prueba_a"]])
            try:
                sent = message.send(fail_silently=False)
            except Exception as exc:
                raise CommandError("No se pudo enviar el correo de prueba; revisa la configuración privada.") from exc
            if sent != 1:
                raise CommandError("SMTP no confirmó el mensaje de prueba.")
            self.stdout.write("Correo sintético de prueba enviado una vez.")
            return
        if options["confirmar_prueba"] or not options["confirmar_envios"]:
            raise CommandError("La cola requiere --confirmar-envios; no se envió ningún correo.")
        if not settings.AVISOS_CORREO_HABILITADOS:
            raise CommandError("Los avisos de correo siguen deshabilitados.")
        if not 1 <= options["limite"] <= 20 or (options["solo_id"] is not None and options["solo_id"] < 1):
            raise CommandError("Límite o ID fuera de rango.")
        result = procesar_pendientes(options["limite"], options["solo_id"])
        self.stdout.write(str(result))
