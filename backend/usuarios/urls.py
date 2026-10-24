from django.urls import path
from .api import CSRFView, LoginView, LogoutView, MeView, RegistroView

app_name = "usuarios"
urlpatterns = [
    path("csrf/", CSRFView.as_view(), name="csrf"),
    path("registro/", RegistroView.as_view(), name="registro"),
    path("login/", LoginView.as_view(), name="login"),
    path("me/", MeView.as_view(), name="me"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
