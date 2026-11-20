"""Ejecución acotada de una fuente institucional; nunca publica convocatorias."""
from urllib.robotparser import RobotFileParser

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from convocatorias.siau_red import AccessError, SourceBackoff, AGENT
from .models import Acceso, Ejecucion, Publicacion
from .observaciones import identity, observe
from .portal_fuentes import links, sections, extract_portal, extract_section, admitted_url, choose_candidates
from .siau_ajax import robots_allowed
from .storage import root_path
from .portal_generico import discover


def capture(execution, source, portal):
    from .services import PersistentDownloader, incident
    try:
        root_path()
        downloader = PersistentDownloader(execution, source)
        robots = downloader.fetch(portal.robots)
        parser = RobotFileParser(portal.robots)
        parser.parse(robots['contenido'].decode('utf-8-sig').splitlines())
        delay = parser.crawl_delay(AGENT) or 0
        if delay > 60:
            raise AccessError('crawl-delay supera el presupuesto de la fuente.')
        downloader.pause = max(downloader.pause, delay)
        root = f'https://{portal.host}'

        def download(url):
            allowed = lambda candidate: robots_allowed(robots['contenido'], candidate, root=root)
            if not allowed(url):
                entry = {'consulta_utc': timezone.now().isoformat()}
                access = downloader.record(url, entry, None, 'bloqueado', error='ROBOTS')
                incident(execution, 'ROBOTS', 'Ruta bloqueada por robots.', access)
                raise AccessError('robots no autoriza la ruta.')
            return downloader.fetch(url, can_fetch=allowed)

        index = download(portal.indice)
        cached_pages = {}
        if portal.generico:
            pages, found_sections, cached_pages = discover(portal, index, download, downloader,
                lambda code, detail: incident(execution, code, detail, severity='aviso'))
        else:
            pages = links(index['contenido'], portal.indice, portal)
            found_sections = {section.identidad: section for section in sections(index['contenido'], portal)}
            pages = list(dict.fromkeys([*pages, *found_sections]))
        known = dict(Publicacion.objects.filter(fuente=source, url_normalizada__in=pages)
                     .values_list('url_normalizada', 'ultima_deteccion'))
        pages, truncated = choose_candidates(pages, known, portal.max_fichas)
        if truncated:
            incident(execution, 'INDICE_LIMITE', 'Índice institucional con cobertura parcial.', severity='aviso')
        html_pages = [url for url in pages if url not in found_sections]
        downloader.pages.update(html_pages)
        downloader.allowed_urls.update(html_pages)
        if not pages:
            incident(execution, 'INDICE_ESTRUCTURA', 'Sin fichas admitidas por el contrato del portal.')
        downloaded_documents = set()
        document_cache = {}
        for url in pages:
            section = found_sections.get(url)
            resource_url = url.split('#becanexo-', 1)[0] if section else url
            downloader.page_url = None if section else url
            downloader.publication = Publicacion.objects.filter(fuente=source, url_normalizada=url).first()
            try:
                other = Publicacion.objects.filter(url_normalizada=url).exclude(fuente=source).first()
                if other:
                    incident(execution, 'DUPLICADO_ENTRE_FUENTES', 'Misma URL ya observada en otra fuente; revisión editorial.', severity='aviso')
                    continue
                page = cached_pages.get(resource_url) if portal.generico else (index if section else download(url))
                if page is None:
                    page = download(resource_url)
                html_access = Acceso.objects.filter(ejecucion=execution, url_normalizada=resource_url, documento__isnull=False).select_related('documento').latest('id')
                if portal.generico and not section and Publicacion.objects.filter(
                        versiones__documentos__documento=html_access.documento).exclude(url_normalizada=url).exists():
                    incident(execution, 'DUPLICADO_CONTENIDO', 'HTML idéntico a otra ficha de la fuente.', severity='aviso')
                    continue
                if downloader.publication is None:
                    if section:
                        downloader.publication = Publicacion.objects.create(
                            fuente=source, url_original=resource_url, url_normalizada=url,
                            normalizacion_version='portal-seccion/1')
                    else:
                        downloader.publication = identity(execution, url)
                publication = downloader.publication
                item = extract_section(page, portal, section) if section else extract_portal(page, portal)
                if portal.generico:
                    item['version_extractor'] = execution.version_extractor
                evidence = [{'rol': 'ficha_html', 'url': resource_url, 'url_original': resource_url,
                             'documento': html_access.documento,
                             'localizador': url.removeprefix(resource_url + '#') if section else None}]
                pending = []
                for link in item['enlaces_bases']:
                    document_url = link['url']
                    if not admitted_url(portal, document_url, 'documento'):
                        pending.append({'url': document_url, 'estado': 'fuera_de_lista'})
                        incident(execution, 'BASE_NO_PERMITIDA', 'Referencia documental conservada sin descarga.', publication=publication, severity='aviso')
                        continue
                    if document_url not in downloaded_documents and len(downloaded_documents) >= 8:
                        pending.append({'url': document_url, 'estado': 'fuera_de_lista'})
                        incident(execution, 'DOCUMENTOS_LIMITE', 'Presupuesto documental agotado.', publication=publication, severity='aviso')
                        continue
                    downloader.pdfs.add(document_url)
                    downloader.allowed_urls.add(document_url)
                    try:
                        if document_url not in document_cache:
                            downloaded_documents.add(document_url)
                            pdf = download(document_url)
                            pdf_access = Acceso.objects.filter(ejecucion=execution, url_normalizada=pdf['url'], documento__isnull=False).select_related('documento').latest('id')
                            document_cache[document_url] = pdf_access.documento
                        evidence.append({'rol': 'bases_pdf', 'url': document_url, 'url_original': document_url,
                                         'documento': document_cache[document_url]})
                    except SourceBackoff:
                        raise
                    except (AccessError, ValueError):
                        pending.append({'url': document_url, 'estado': 'inaccesible'})
                        incident(execution, 'BASE_INACCESIBLE', 'Documento pendiente de revisión.', publication=publication, severity='aviso')
                observation = observe(execution, publication, item, evidence, pending)
                if portal.generico and observation.resultado != 'sin_cambios':
                    from .auto_borradores import candidate_assessment
                    admitted, reason = candidate_assessment(publication, observation.version)
                    incident(execution, 'CANDIDATO_ACEPTADO' if admitted else
                             'CANDIDATO_FUERA_ALCANCE' if (reason or '').startswith('Descartada') else 'CANDIDATO_PENDIENTE',
                             (reason or 'Ficha con evidencia suficiente para borrador privado.') if admitted else (reason or 'Revisión editorial pendiente.'),
                             publication=publication, severity='aviso')
                if observation.version_id and getattr(settings, 'RASTREO_BORRADORES_AUTOMATICOS_HABILITADOS', False):
                    try:
                        from .auto_borradores import prepare_automatic_draft
                        origin, _, reason = prepare_automatic_draft(publication.pk, observation.version_id)
                        if reason and observation.resultado != 'sin_cambios':
                            code = ('BORRADOR_REVISION_PENDIENTE' if origin else
                                    'CANDIDATO_FUERA_ALCANCE' if reason.startswith('Descartada') else 'CANDIDATO_PENDIENTE')
                            incident(execution, code, reason, publication=publication, severity='aviso')
                    except Exception as exc:
                        incident(execution, 'BORRADOR_AUTO_FALLIDO', type(exc).__name__, publication=publication)
            except SourceBackoff:
                raise
            except (AccessError, ValueError, ValidationError) as exc:
                incident(execution, 'FICHA_INCOMPLETA', type(exc).__name__, publication=downloader.publication)
            finally:
                downloader.publication = None
                downloader.page_url = None
        failures = execution.incidencias.filter(gravedad='error').exists()
        state = 'parcial' if failures else 'finalizada'
        if not execution.accesos.filter(documento__isnull=False).exists():
            state = 'fallida'
        Ejecucion.objects.filter(pk=execution.pk).update(estado=state, fin=timezone.now())
    except Exception as exc:
        incident(execution, 'EJECUCION_FALLIDA', type(exc).__name__)
        Ejecucion.objects.filter(pk=execution.pk).update(estado='fallida', fin=timezone.now(), error_resumen=type(exc).__name__)
    return execution
