from django.urls import path
from .api import CSRFView, LoginView, LogoutView, MeView, RecuperarContrasenaView, RegistroView, RestablecerContrasenaView

app_name = "usuarios"
urlpatterns = [
    path("csrf/", CSRFView.as_view(), name="csrf"),
    path("registro/", RegistroView.as_view(), name="registro"),
    path("login/", LoginView.as_view(), name="login"),
    path("me/", MeView.as_view(), name="me"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("recuperar-contrasena/", RecuperarContrasenaView.as_view(), name="recuperar-contrasena"),
    path("restablecer-contrasena/", RestablecerContrasenaView.as_view(), name="restablecer-contrasena"),
]
