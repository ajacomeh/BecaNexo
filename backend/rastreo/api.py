"""Consulta y revisión administrativa; sin publicación ni ejecución de rastreo."""
import hashlib
from urllib.parse import urlsplit

from django.db.models import F, OuterRef, Subquery, Q, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from usuarios.api import AuthView
from convocatorias.api import Administrador, parametros, entero, paginar
from .models import Fuente, Publicacion, Version, VersionDocumento, Observacion, Ejecucion, Acceso, Incidencia, Documento, CandidatoIndice
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


DECISION_CODES = ('CANDIDATO_FUERA_ALCANCE', 'CANDIDATO_PENDIENTE')


def latest_publications():
    last = Observacion.objects.filter(publicacion_id=OuterRef('pk'), version__isnull=False).order_by('-observada_en', '-id')
    decision = Incidencia.objects.filter(publicacion_id=OuterRef('pk'), codigo__in=DECISION_CODES).order_by('-detectada_en', '-id')
    return Publicacion.objects.select_related('fuente').annotate(
        version_observada_id=Subquery(last.values('version_id')[:1]),
        titulo_observado=Subquery(last.values('version__datos_extraidos__titulo__texto_original')[:1]),
        borrador_convocatoria_id=F('borrador_automatico__convocatoria_id'),
        decision_codigo=Subquery(decision.values('codigo')[:1]),
        decision_motivo=Subquery(decision.values('detalle')[:1]))


def publication_data(p):
    title = p.titulo_observado
    return {'id': p.pk, 'fuente': {'id': p.fuente_id, 'nombre': p.fuente.nombre},
            'titulo': title if isinstance(title, str) and title.strip() else urlsplit(p.url_original).path or p.url_original,
            'url_original': p.url_original, 'primera_deteccion': p.primera_deteccion, 'ultima_deteccion': p.ultima_deteccion,
            'version_observada_id': p.version_observada_id, 'convocatoria_id': p.convocatoria_id,
            'situacion': publication_situation(p)}


def publication_situation(p, classify=False):
    """Situación editorial visible: borrador o motivo claro de que no lo tenga.

    En la lista usa solo valores anotados en la misma consulta; el detalle (classify=True)
    recalcula la clasificación vigente con la última versión observada.
    """
    if p.borrador_convocatoria_id:
        from convocatorias.models import BorradorRastreo
        from convocatorias.services import descartado
        from .auto_borradores import oferente_externo
        origin = BorradorRastreo.objects.select_related('convocatoria').get(convocatoria_id=p.borrador_convocatoria_id)
        no_ec, nombre = oferente_externo(origin)
        return {'tipo': 'borrador', 'convocatoria_id': p.borrador_convocatoria_id, 'motivo': None,
                'pendientes': len(origin.pendientes_iniciales or []),
                'oferente_no_ecuatoriano': no_ec and not origin.convocatoria.institucion_id, 'oferente_detectado': nombre or None,
                'descartado': descartado(origin.convocatoria)}
    if p.convocatoria_id:
        return {'tipo': 'integrada', 'convocatoria_id': p.convocatoria_id, 'motivo': None}
    if not p.version_observada_id:
        return {'tipo': 'sin_version', 'convocatoria_id': None,
                'motivo': 'Sin borrador: todavía no hay una versión conservada de la ficha.'}
    if classify:
        from .auto_borradores import classify_candidate
        result = classify_candidate(p, Version.objects.get(pk=p.version_observada_id))
        kind = 'descartada' if result['estado'] == 'fuera_alcance' else 'sin_borrador' if result['estado'] != 'apta' else 'apta_sin_borrador'
        return {'tipo': kind, 'convocatoria_id': None,
                'motivo': result['motivo'] if kind != 'apta_sin_borrador'
                else 'Apta para borrador; se creará en la próxima captura con borradores automáticos habilitados.'}
    if p.decision_codigo:
        return {'tipo': 'descartada' if p.decision_codigo == 'CANDIDATO_FUERA_ALCANCE' else 'sin_borrador',
                'convocatoria_id': None, 'motivo': p.decision_motivo}
    return {'tipo': 'sin_borrador', 'convocatoria_id': None,
            'motivo': 'Sin borrador todavía; abre la publicación para ver su clasificación.'}


def execution_data(e):
    return {**{f: getattr(e, f) for f in ('id', 'estado', 'inicio', 'fin', 'publicaciones_observadas', 'versiones_nuevas', 'observaciones_sin_cambios')},
            'fuente': {'id': e.fuente_id, 'nombre': e.fuente.nombre},
            'accesos': e.accesos_total, 'documentos_distintos': e.documentos_total,
            'tipo': 'metadatos_indice' if e.version_extractor == 'siau-index-meta/1' else 'documental',
            'candidatos_registrados': e.candidatos_total,
            # Campos nuevos (los anteriores no cambian): versiones con contenido nuevo (primera observación o cambio
            # relevante) y cambios técnicos (nueva versión por cambio de extractor, normalizador o contrato).
            'versiones_con_cambios': e.con_cambios_total, 'cambios_tecnicos': e.tecnicos_total,
            # Contadores por gravedad: «parcial» solo se debe a incidencias de error (fallos reales).
            'incidencias_error': e.errores_total, 'incidencias_aviso': e.avisos_total}


def executions():
    return Ejecucion.objects.select_related('fuente').annotate(
        accesos_total=Count('accesos', distinct=True),
        documentos_total=Count('accesos__documento', distinct=True),
        candidatos_total=Count('candidatoindice', distinct=True),
        con_cambios_total=Count('observaciones', filter=Q(observaciones__resultado__in=('nueva', 'cambio_relevante')), distinct=True),
        tecnicos_total=Count('observaciones', filter=Q(observaciones__resultado='cambio_bytes'), distinct=True),
        errores_total=Count('incidencias', filter=Q(incidencias__gravedad='error'), distinct=True),
        avisos_total=Count('incidencias', filter=Q(incidencias__gravedad='aviso'), distinct=True))


class ReadOnly(AuthView):
    permission_classes = [AdministradorActivo]
    http_method_names = ['get', 'options']


class Fuentes(ReadOnly):
    def get(self, request):
        parametros(request, {'page', 'page_size'})
        def data(source):
            last = source.ejecucion_set.order_by('-inicio', '-id').first()
            return {'id': source.pk, 'nombre': source.nombre, 'adaptador': source.adaptador,
                    'activa': source.activa, 'politica_version': source.politica_version,
                    'frecuencia_min': source.frecuencia_min,
                    'ultima_ejecucion': {'id': last.pk, 'estado': last.estado, 'inicio': last.inicio} if last else None,
                    'publicaciones': source.publicacion_set.count(),
                    'borradores': source.publicacion_set.filter(borrador_automatico__isnull=False).count()}
        return paginar(request, Fuente.objects.order_by('nombre', 'id'), data)


class CandidatosIndice(ReadOnly):
    """Metadatos del índice: no equivalen a fichas verificadas ni a borradores."""
    def get(self, request):
        parametros(request, {'page', 'page_size', 'fuente', 'ejecucion'})
        rows = CandidatoIndice.objects.select_related('fuente').order_by('-ultima_deteccion', '-id')
        if 'fuente' in request.query_params:
            rows = rows.filter(fuente_id=entero(request.query_params, 'fuente', None))
        if 'ejecucion' in request.query_params:
            rows = rows.filter(ultima_ejecucion_id=entero(request.query_params, 'ejecucion', None))
        return paginar(request, rows, lambda row: {
            'id': row.pk, 'fuente_id': row.fuente_id, 'fuente': row.fuente.nombre,
            'titulo': row.titulo_publico,
            'url': row.url_normalizada, 'pagina': row.pagina,
            'primera_deteccion': row.primera_deteccion, 'ultima_deteccion': row.ultima_deteccion,
            'ejecucion_id': row.ultima_ejecucion_id, 'respuesta_sha256': row.respuesta_sha256,
            'estado': 'pendiente', 'motivo': 'Ficha, vigencia, oferente y requisitos sin verificar.'})


class Publicaciones(ReadOnly):
    def get(self, request, pk=None):
        if pk is not None:
            parametros(request, set())
            publication = identified(latest_publications(), pk)
            result = publication_data(publication)
            result['situacion'] = publication_situation(publication, classify=True)
            if publication.version_observada_id:
                from .auto_borradores import classify_candidate
                version = Version.objects.get(pk=publication.version_observada_id)
                result['clasificacion_borrador'] = classify_candidate(publication, version)
                result['cierre_extraido'] = (version.datos_extraidos or {}).get('cierre')
            if publication.convocatoria_id:
                from convocatorias.models import Convocatoria, BorradorRastreo
                from .auto_borradores import review_notes
                offer = Convocatoria.objects.get(pk=publication.convocatoria_id)
                origin = BorradorRastreo.objects.filter(publicacion=publication, convocatoria=offer).select_related('version').first()
                from convocatorias.services import errores_publicacion
                blockers = errores_publicacion(offer, estricto=False)
                result['borrador'] = {'id': offer.pk, 'revision': offer.revision, 'activa': offer.activa,
                    'bloqueos': blockers,
                    'observaciones': review_notes(offer, origin) if origin else []}
            return Response(result)
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


PAGINA_DETALLE = 25  # Detalle de ejecución: 25 por página por defecto (máximo 50).
GRAVEDADES = ('error', 'aviso')


class Accesos(ReadOnly):
    def get(self, request, pk):
        parametros(request, {'page', 'page_size'})
        identified(Ejecucion, pk)
        return paginar(request, Acceso.objects.filter(ejecucion_id=pk).order_by('secuencia'),
            lambda a: {f: getattr(a, f) for f in ('id', 'secuencia', 'rol', 'url_original', 'http_status', 'resultado', 'documento_id', 'publicacion_id', 'inicio_peticion_en', 'fin')},
            default_size=PAGINA_DETALLE)


class Incidencias(ReadOnly):
    def get(self, request, pk):
        parametros(request, {'page', 'page_size', 'gravedad', 'codigo'})
        identified(Ejecucion, pk)
        todas = Incidencia.objects.filter(ejecucion_id=pk)
        filtro = {}
        if 'gravedad' in request.query_params:
            if request.query_params['gravedad'] not in GRAVEDADES:
                raise serializers.ValidationError({'gravedad': 'Usa error o aviso.'})
            filtro['gravedad'] = request.query_params['gravedad']
        if 'codigo' in request.query_params:
            codigo = request.query_params['codigo']
            if not 0 < len(codigo) <= 60:
                raise serializers.ValidationError({'codigo': 'Código no válido.'})
            filtro['codigo'] = codigo
        # Código y gravedad son suficientes; no trasladar posibles mensajes técnicos internos.
        response = paginar(request, todas.filter(**filtro).order_by('id'),
            lambda i: {f: getattr(i, f) for f in ('id', 'codigo', 'gravedad', 'detectada_en', 'publicacion_id', 'version_id')},
            default_size=PAGINA_DETALLE)
        # Resumen agrupado de toda la ejecución (no depende de los filtros): errores primero y luego por frecuencia.
        grupos = todas.values('codigo', 'gravedad').annotate(total=Count('id'))
        response.data['resumen'] = sorted(({'codigo': g['codigo'], 'gravedad': g['gravedad'], 'total': g['total']} for g in grupos),
                                          key=lambda g: (g['gravedad'] != 'error', -g['total'], g['codigo']))
        return response


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
