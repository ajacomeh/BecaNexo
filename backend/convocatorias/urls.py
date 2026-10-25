from django.urls import path
from . import api

urlpatterns = [
    path("becas/catalogos/", api.Catalogos.as_view()),
    path("becas/", api.Consulta.as_view()), path("becas/<int:pk>/", api.Consulta.as_view()),
    path("gestion/instituciones/", api.Instituciones.as_view()),
    path("gestion/instituciones/<int:pk>/", api.Instituciones.as_view()),
    path("gestion/convocatorias/", api.Convocatorias.as_view()),
    path("gestion/convocatorias/<int:pk>/", api.Convocatorias.as_view()),
    path("gestion/convocatorias/<int:pk>/auditoria/", api.Auditoria.as_view()),
]
for accion in ("publicar", "pausar"):
    urlpatterns.append(path(f"gestion/convocatorias/<int:pk>/{accion}/", api.Accion.as_view(), {"accion": accion}))
for recurso in api.RECURSOS:
    urlpatterns += [path(f"gestion/convocatorias/<int:convocatoria>/{recurso}/", api.Hijos.as_view(recurso=recurso)),
                    path(f"gestion/convocatorias/<int:convocatoria>/{recurso}/<int:pk>/", api.Hijos.as_view(recurso=recurso))]
