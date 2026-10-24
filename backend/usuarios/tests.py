from django.contrib import admin
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import identify_hasher
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, SimpleTestCase, TestCase

from .admin import UsuarioAdmin
from .forms import UsuarioChangeForm, UsuarioCreationForm
from .models import Usuario


PASSWORD = "Solo-Pruebas!Lago-4827"


class UsuarioSinBaseTests(SimpleTestCase):
    def test_campos_obligatorios(self):
        for email, nombre in [("", "Ana"), ("   ", "Ana"), (None, "Ana"),
                              ("ana@example.com", ""), ("ana@example.com", "  "),
                              ("ana@example.com", None)]:
            with self.subTest(email=email, nombre=nombre), self.assertRaises(ValidationError):
                Usuario.objects.create_user(email, nombre, PASSWORD)

    def test_normalizacion_y_hash(self):
        user = Usuario(email="  Ana@EXAMPLE.COM  ", nombre=" Ana ")
        user.clean()
        self.assertEqual(user.email, "ana@example.com")
        self.assertEqual(user.nombre, "Ana")
        user.set_password(PASSWORD)
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertTrue(identify_hasher(user.password))

    def test_superusuario_rechaza_contradicciones(self):
        for field, value in [("rol", "postulante"), ("is_active", False),
                             ("is_staff", False), ("is_superuser", False)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                Usuario.objects.create_superuser("admin@example.com", "Admin", PASSWORD, **{field: value})
        with self.assertRaises(ValueError):
            Usuario.objects.create_superuser("admin@example.com", "Admin")

    def test_manager_valida_contrasena(self):
        with self.assertRaises(ValidationError):
            Usuario.objects.create_user("ana@example.com", "Ana", "123")

    def test_rol_invalido(self):
        with self.assertRaises(ValidationError):
            Usuario.objects.create_user("ana@example.com", "Ana", PASSWORD, rol="otro")

    def test_admin_no_permite_a_staff_modificar_cuentas(self):
        request = RequestFactory().get("/admin/")
        request.user = Usuario(is_staff=True, rol=Usuario.Rol.ADMINISTRADOR)
        model_admin = UsuarioAdmin(Usuario, admin.site)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_formularios_sin_username(self):
        self.assertNotIn("username", UsuarioCreationForm().fields)
        self.assertNotIn("username", UsuarioChangeForm().fields)


class UsuarioBaseTests(TestCase):
    def crear(self, **kwargs):
        return Usuario.objects.create_user("ana@example.com", "Ana", PASSWORD, **kwargs)

    def test_creacion_y_hash_persistido(self):
        user = Usuario.objects.create_user("  ANA@Example.COM  ", " Ana ", PASSWORD)
        user.refresh_from_db()
        self.assertEqual(user.email, "ana@example.com")
        self.assertEqual(user.nombre, "Ana")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.rol, "postulante")
        self.assertIsNotNone(user.creado_en)

    def test_duplicado_manager(self):
        self.crear()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.create_user(" ANA@EXAMPLE.COM ", "Otra", PASSWORD)

    def test_restriccion_email_sin_normalizacion_python(self):
        self.crear()
        other = Usuario.objects.create_user("otra@example.com", "Otra", PASSWORD)
        for email in ["ANA@EXAMPLE.COM", " ana@example.com "]:
            with self.subTest(email=email), self.assertRaises(IntegrityError), transaction.atomic():
                Usuario.objects.filter(pk=other.pk).update(email=email)

    def test_autenticacion(self):
        user = self.crear()
        for email in ["ana@example.com", "ANA@EXAMPLE.COM", "  Ana@Example.Com  "]:
            with self.subTest(email=email):
                self.assertEqual(authenticate(email=email, password=PASSWORD), user)
        # El formulario de login de Django Admin usa esta clave técnica.
        self.assertEqual(authenticate(username=" ANA@EXAMPLE.COM ", password=PASSWORD), user)
        self.assertIsNone(authenticate(email=user.email, password="incorrecta"))
        self.assertIsNone(authenticate(email="ausente@example.com", password=PASSWORD))

    def test_inactivo_no_autentica(self):
        self.crear(is_active=False)
        self.assertIsNone(authenticate(email="ANA@EXAMPLE.COM", password=PASSWORD))

    def test_superusuario(self):
        user = Usuario.objects.create_superuser(" ADMIN@EXAMPLE.COM ", "Admin", PASSWORD)
        user.refresh_from_db()
        self.assertEqual(user.rol, "administrador")
        self.assertTrue(user.is_active and user.is_staff and user.is_superuser)
        self.assertTrue(user.check_password(PASSWORD))

    def test_roles_y_restricciones_base(self):
        user = self.crear(rol="administrador")
        self.assertFalse(user.is_staff)
        for rol in ["postulante", "administrador"]:
            Usuario.objects.filter(pk=user.pk).update(rol=rol)
        for fields in [{"rol": "otro"}, {"rol": ""}, {"nombre": "  "}, {"email": "  "}]:
            with self.subTest(fields=fields), self.assertRaises(IntegrityError), transaction.atomic():
                Usuario.objects.filter(pk=user.pk).update(**fields)

    def test_formulario_creacion_hash_y_validacion(self):
        data = {"email": " ANA@EXAMPLE.COM ", "nombre": "Ana", "rol": "postulante",
                "is_active": True, "password1": PASSWORD, "password2": PASSWORD}
        form = UsuarioCreationForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.check_password(PASSWORD))
        duplicate = UsuarioCreationForm(data={**data, "email": "Ana@example.com"})
        self.assertFalse(duplicate.is_valid())
        for first, second in [("123", "123"), (PASSWORD, "diferente")]:
            form = UsuarioCreationForm(data={**data, "email": "otra@example.com",
                                             "password1": first, "password2": second})
            self.assertFalse(form.is_valid())
            self.assertIn("password2", form.errors)

    def test_formulario_edicion_no_sobrescribe_hash(self):
        user = self.crear()
        form = UsuarioChangeForm(instance=user, data={"email": user.email, "nombre": "Ana Dos",
            "rol": "postulante", "is_active": True, "password": "texto-inyectado"})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        self.assertTrue(user.check_password(PASSWORD))
