from django.urls import path
from .api import Bandeja, MarcarLeida

urlpatterns = [
    path("", Bandeja.as_view()),
    path("<int:pk>/leer/", MarcarLeida.as_view()),
]
