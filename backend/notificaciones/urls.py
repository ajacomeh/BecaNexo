from django.urls import path
from .api import Bandeja, MarcarLeida, PreferenciaEmail

urlpatterns = [
    path("", Bandeja.as_view()),
    path("correo/", PreferenciaEmail.as_view()),
    path("<int:pk>/leer/", MarcarLeida.as_view()),
]
