"""Consulta y revisión administrativa; sin publicación ni ejecución de rastreo."""
import hashlib
from urllib.parse import urlsplit

from django.db.models import OuterRef, Subquery, Q, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from usuarios.api import AuthView
from convocatorias.api import Administrador, parametros, entero, paginar
from .models import Fuente, Publicacion, Version, VersionDocumento, Observacion, Ejecucion, Acceso, Incidencia, Documento
from .storage import root_path, key_for, verify_file, StorageError
from .models import Revision
from .revisiones import RevisionEntrada, registrar, revision_data, vigentes


class AdministradorActivo(Administrador):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.is_active


def identified(model, pk):
    if not 0 < pk <= 9223372036854775807:
        raise serializers.ValidationError({'id': 'Identificador fuera de rango.'})
    return get_object_or_404(model, pk=pk)


def latest_publications():
    last = Observacion.objects.filter(publicacion_id=OuterRef('pk'), version__isnull=False).order_by('-observada_en', '-id')
    return Publicacion.objects.select_related('fuente').annotate(
        version_observada_id=Subquery(last.values('version_id')[:1]),
        titulo_observado=Subquery(last.values('version__datos_extraidos__titulo__texto_original')[:1]))


def publication_data(p):
    title = p.titulo_observado
    return {'id': p.pk, 'fuente': {'id': p.fuente_id, 'nombre': p.fuente.nombre},
            'titulo': title if isinstance(title, str) and title.strip() else urlsplit(p.url_original).path or p.url_original,
            'url_original': p.url_original, 'primera_deteccion': p.primera_deteccion, 'ultima_deteccion': p.ultima_deteccion,
            'version_observada_id': p.version_observada_id, 'convocatoria_id': p.convocatoria_id}


def execution_data(e):
    return {**{f: getattr(e, f) for f in ('id', 'estado', 'inicio', 'fin', 'publicaciones_observadas', 'versiones_nuevas', 'observaciones_sin_cambios')},
            'fuente': {'id': e.fuente_id, 'nombre': e.fuente.nombre},
            'accesos': e.accesos_total, 'documentos_distintos': e.documentos_total}


def executions():
    return Ejecucion.objects.select_related('fuente').annotate(accesos_total=Count('accesos'), documentos_total=Count('accesos__documento', distinct=True))


class ReadOnly(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['get', 'options']


class Fuentes(ReadOnly):
    def get(self, request):
        parametros(request, {'page', 'page_size'})
        return paginar(request, Fuente.objects.order_by('nombre', 'id'), lambda f: {'id': f.pk, 'nombre': f.nombre})


class Publicaciones(ReadOnly):
    def get(self, request, pk=None):
        if pk is not None:
            parametros(request, set())
            return Response(publication_data(identified(latest_publications(), pk)))
        parametros(request, {'page', 'page_size', 'q', 'fuente'})
        qs = latest_publications()
        query = request.query_params.get('q', '').strip()
        if len(query) > 200:
            raise serializers.ValidationError({'q': 'Máximo 200 caracteres.'})
        if query:
            qs = qs.filter(Q(titulo_observado__icontains=query) | Q(url_original__icontains=query))
        if 'fuente' in request.query_params:
            qs = qs.filter(fuente_id=entero(request.query_params, 'fuente', None))
        return paginar(request, qs.order_by('-ultima_deteccion', '-id'), publication_data)


class Versiones(ReadOnly):
    def get(self, request, pk):
        parametros(request, {'page', 'page_size'})
        p = identified(Publicacion, pk)
        return paginar(request, p.versiones.order_by('-numero'), lambda v: {f: getattr(v, f) for f in ('id', 'numero', 'creada_en', 'estado_extraccion', 'version_extractor')})


class VersionDetalle(ReadOnly):
    def get(self, request, pk, version_id):
        parametros(request, set())
        identified(Publicacion, pk)
        v = identified(Version.objects.filter(publicacion_id=pk), version_id)
        return Response({f: getattr(v, f) for f in ('id', 'numero', 'creada_en', 'estado_extraccion', 'version_extractor', 'version_normalizador', 'version_contrato', 'datos_extraidos', 'texto_extraido', 'advertencias')})


class DocumentosVersion(ReadOnly):
    def get(self, request, pk, version_id):
        parametros(request, {'page', 'page_size'})
        identified(Publicacion, pk)
        v = identified(Version.objects.filter(publicacion_id=pk), version_id)
        return paginar(request, VersionDocumento.objects.filter(version=v).select_related('documento').order_by('id'),
            lambda r: {'id': r.documento_id, 'evidencia_id': r.pk, 'rol': r.rol, 'url_original': r.url_original,
                       'mime': r.documento.mime, 'tamano_bytes': r.documento.tamano_bytes, 'sha256': r.documento.sha256})


class Observaciones(ReadOnly):
    def get(self, request, pk):
        parametros(request, {'page', 'page_size'})
        p = identified(Publicacion, pk)
        return paginar(request, p.observaciones.select_related('ejecucion').order_by('-observada_en', '-id'),
            lambda o: {'id': o.pk, 'ejecucion_id': o.ejecucion_id, 'estado_ejecucion': o.ejecucion.estado,
                       'version_id': o.version_id, 'observada_en': o.observada_en, 'resultado': o.resultado})


class Ejecuciones(ReadOnly):
    def get(self, request, pk=None):
        if pk is not None:
            parametros(request, set())
            return Response(execution_data(identified(executions(), pk)))
        parametros(request, {'page', 'page_size'})
        return paginar(request, executions().order_by('-inicio', '-id'), execution_data)


class Accesos(ReadOnly):
    def get(self, request, pk):
        parametros(request, {'page', 'page_size'})
        identified(Ejecucion, pk)
        return paginar(request, Acceso.objects.filter(ejecucion_id=pk).order_by('secuencia'),
            lambda a: {f: getattr(a, f) for f in ('id', 'secuencia', 'rol', 'url_original', 'http_status', 'resultado', 'documento_id', 'publicacion_id', 'inicio_peticion_en', 'fin')})


class Incidencias(ReadOnly):
    def get(self, request, pk):
        parametros(request, {'page', 'page_size'})
        identified(Ejecucion, pk)
        # Código y gravedad son suficientes; no trasladar posibles mensajes técnicos internos.
        return paginar(request, Incidencia.objects.filter(ejecucion_id=pk).order_by('id'),
            lambda i: {f: getattr(i, f) for f in ('id', 'codigo', 'gravedad', 'detectada_en', 'publicacion_id', 'version_id')})


class Descargar(ReadOnly):
    def get(self, request, pk):
        parametros(request, set())
        doc = identified(Documento, pk)
        try:
            root = root_path()
            if doc.clave_almacenamiento != key_for(doc.sha256):
                raise StorageError('Clave inválida')
            path = root / doc.clave_almacenamiento
            if path.parent.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(root):
                raise StorageError('Ruta inválida')
            verify_file(path, doc.sha256, doc.tamano_bytes)
            # Servir exactamente los bytes verificados; tamaño máximo del modelo: 8 MiB.
            data = path.read_bytes()
            if len(data) != doc.tamano_bytes or hashlib.sha256(data).hexdigest() != doc.sha256:
                raise StorageError('Documento inconsistente')
        except (StorageError, OSError):
            return Response({'detail': 'Evidencia no disponible o inconsistente. Solicita verificación del almacenamiento.'}, status=409)
        response = HttpResponse(data, content_type='application/octet-stream')
        extension = {'application/pdf': 'pdf', 'text/html': 'html', 'text/plain': 'txt'}.get(doc.mime, 'bin')
        response['Content-Disposition'] = f'attachment; filename="evidencia-{doc.pk}.{extension}"'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Content-Security-Policy'] = "sandbox; default-src 'none'"
        return response


class Revisiones(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['get', 'post', 'options']

    def version(self, pk, version_id):
        return identified(Version.objects.filter(publicacion_id=pk), version_id)

    def get(self, request, pk, version_id):
        parametros(request, {'page', 'page_size'})
        version = self.version(pk, version_id)
        current = vigentes(version.pk).select_related('actor').order_by('id')
        response = paginar(request, Revision.objects.filter(version=version).select_related('actor').order_by('-creada_en', '-id'), revision_data)
        latest = Observacion.objects.filter(publicacion_id=pk, version__isnull=False).order_by('-observada_en', '-id').first()
        response.data.update(vigentes=[revision_data(r) for r in current],
                             version_id=version.pk, numero=version.numero,
                             ultima_observada=bool(latest and latest.version_id == version.pk))
        return response

    def post(self, request, pk, version_id):
        parametros(request, set())
        version = self.version(pk, version_id)
        serializer = RevisionEntrada(data=request.data)
        serializer.is_valid(raise_exception=True)
        row, created = registrar(request.user.pk, version.pk, serializer.validated_data)
        return Response(revision_data(row), status=201 if created else 200)
