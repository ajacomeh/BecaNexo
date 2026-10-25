from django.urls import path
from .api import CatalogosView, PerfilView, RelacionView, RECURSOS

urlpatterns = [path("", PerfilView.as_view()), path("catalogos/", CatalogosView.as_view())]
for recurso in RECURSOS:
    urlpatterns.extend([
        path(f"{recurso}/", RelacionView.as_view(recurso=recurso, http_method_names=["get", "post", "options"])),
        path(f"{recurso}/<int:pk>/", RelacionView.as_view(recurso=recurso, http_method_names=["get", "patch", "delete", "options"])),
    ])
