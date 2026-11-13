from django.urls import path
from . import api
from . import api_propuestas
from . import api_control

urlpatterns = [
    path('control/', api_control.ControlRastreo.as_view()),
    path('publicaciones/<int:publication>/propuesta/', api_propuestas.Propuestas.as_view()),
    path('propuestas/<int:pk>/', api_propuestas.Propuestas.as_view()),
    path('propuestas/<int:pk>/validar/', api_propuestas.ValidarPropuesta.as_view()),
    path('propuestas/<int:pk>/crear-borrador/', api_propuestas.CrearBorrador.as_view()),
    path('propuestas/<int:pk>/aplicar-borrador/', api_propuestas.AplicarPropuestaBorrador.as_view()),
    path('convocatorias/<int:pk>/origen/', api_propuestas.OrigenBorrador.as_view()),
    path('publicaciones/<int:pk>/versiones/<int:version_id>/revisiones/', api.Revisiones.as_view()),
    path('fuentes/', api.Fuentes.as_view()),
    path('publicaciones/', api.Publicaciones.as_view()),
    path('publicaciones/<int:pk>/', api.Publicaciones.as_view()),
    path('publicaciones/<int:pk>/versiones/', api.Versiones.as_view()),
    path('publicaciones/<int:pk>/versiones/<int:version_id>/', api.VersionDetalle.as_view()),
    path('publicaciones/<int:pk>/versiones/<int:version_id>/documentos/', api.DocumentosVersion.as_view()),
    path('publicaciones/<int:pk>/observaciones/', api.Observaciones.as_view()),
    path('ejecuciones/', api.Ejecuciones.as_view()),
    path('ejecuciones/<int:pk>/', api.Ejecuciones.as_view()),
    path('ejecuciones/<int:pk>/accesos/', api.Accesos.as_view()),
    path('ejecuciones/<int:pk>/incidencias/', api.Incidencias.as_view()),
    path('documentos/<int:pk>/descarga/', api.Descargar.as_view()),
]
