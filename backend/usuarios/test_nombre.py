from secrets import token_urlsafe
from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Usuario


class NombreTests(TestCase):
    def setUp(self):
        self.assertEqual(settings.DATABASES['default']['NAME'], 'test_becanexo_db')
        self.password = token_urlsafe(32)
        self.user = Usuario.objects.create_user('nombre-test@example.com', 'Antes', self.password)
        self.other = Usuario.objects.create_user('otro-nombre@example.com', 'Otro')
        self.client = APIClient(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        self.token = self.client.get('/api/auth/csrf/').data['csrfToken']

    def patch(self, data):
        return self.client.patch('/api/auth/me/', data, format='json', HTTP_X_CSRFTOKEN=self.token)

    def test_own_name_both_roles_persists_session_and_safe_response(self):
        original = Usuario.objects.filter(pk=self.user.pk).values().get()
        for role in ('postulante', 'administrador'):
            self.user.rol = role; self.user.save(update_fields=['rol'])
            result = self.patch({'nombre': "  María José O’Connor-2  "})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data, {'nombre': 'María José O’Connor-2'})
            self.assertIn('no-store', result['Cache-Control'])
            self.assertEqual(self.client.get('/api/auth/me/').data['nombre'], 'María José O’Connor-2')
        after = Usuario.objects.filter(pk=self.user.pk).values().get()
        for key in original.keys() - {'nombre', 'rol'}:
            self.assertEqual(original[key], after[key])
        self.other.refresh_from_db(); self.assertEqual(self.other.nombre, 'Otro')

    def test_anonymous_and_csrf_rejected(self):
        self.assertEqual(self.client.patch('/api/auth/me/', {'nombre': 'Nuevo'}, format='json').status_code, 403)
        self.assertEqual(self.client.patch('/api/auth/me/', {'nombre': 'Nuevo'}, format='json', HTTP_X_CSRFTOKEN='incorrecto').status_code, 403)
        anonymous = APIClient(enforce_csrf_checks=True)
        token = anonymous.get('/api/auth/csrf/').data['csrfToken']
        self.assertEqual(anonymous.patch('/api/auth/me/', {'nombre': 'Nuevo'}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 403)
        self.user.refresh_from_db(); self.assertEqual(self.user.nombre, 'Antes')

    def test_validation(self):
        for value in ('', '  \t\n', 'a' * 181, None, 123, True, [], {}):
            with self.subTest(value=value):
                self.assertEqual(self.patch({'nombre': value}).status_code, 400)
        self.assertEqual(self.patch({}).status_code, 400)
        self.assertEqual(self.patch({'nombre': 'Á' * 180}).status_code, 200)

    def test_extra_fields_rejected_without_changes(self):
        self.assertEqual(self.client.patch('/api/auth/me/?id=' + str(self.other.pk), {'nombre': 'Cambio'}, format='json', HTTP_X_CSRFTOKEN=self.token).status_code, 400)
        for key in ('id', 'usuario', 'email', 'password', 'rol', 'is_staff', 'is_superuser', 'is_active', 'groups', 'user_permissions', 'activo'):
            self.assertEqual(self.patch({'nombre': 'Cambio', key: self.other.pk}).status_code, 400)
        self.user.refresh_from_db(); self.other.refresh_from_db()
        self.assertEqual(self.user.nombre, 'Antes'); self.assertEqual(self.other.nombre, 'Otro')

    def test_real_login_patch_logout_and_new_session(self):
        client = APIClient(enforce_csrf_checks=True)
        token = client.get('/api/auth/csrf/').data['csrfToken']
        login = client.post('/api/auth/login/', {'email': self.user.email, 'password': self.password}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(login.status_code, 200)
        token = login.data['csrfToken']
        result = client.patch('/api/auth/me/', {'nombre': 'Nombre persistido'}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(client.get('/api/auth/me/').data['nombre'], 'Nombre persistido')
        self.assertEqual(client.post('/api/auth/logout/', {}, format='json', HTTP_X_CSRFTOKEN=token).status_code, 204)
        fresh = APIClient(enforce_csrf_checks=True)
        token = fresh.get('/api/auth/csrf/').data['csrfToken']
        result = fresh.post('/api/auth/login/', {'email': self.user.email, 'password': self.password}, format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(fresh.get('/api/auth/me/').data['nombre'], 'Nombre persistido')
