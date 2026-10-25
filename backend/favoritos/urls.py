from django.urls import path
from .api import Lista, Quitar

urlpatterns = [path("", Lista.as_view()), path("<int:pk>/", Quitar.as_view())]
