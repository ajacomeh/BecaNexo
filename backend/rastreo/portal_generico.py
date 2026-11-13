"""Exploración acotada de una fuente institucional previamente autorizada.

El índice se vuelve a visitar en cada ciclo; una página sin ficha académica no
se convierte en publicación. La red, robots y la persistencia siguen en el runner.
"""
import re
from collections import deque
from urllib.parse import urljoin

from convocatorias.siau_red import AccessError, SourceBackoff
from .portal_fuentes import Links, Text, admitted_url, sections


RELEVANT = re.compile(r'\bbecas?\b|\bconvocatorias?\b|financiamiento acad[eé]mico|ayuda econ[oó]mica', re.I)
NEGATIVE = re.compile(r'\b(noticias?|bolet[ií]n|evento|premiaci[oó]n|ganadores?)\b', re.I)
CATEGORY = re.compile(r'^\s*becas?(?:\s+(?:disponibles|estudiantiles|universitarias|nacionales|internacionales))?\s*$', re.I)


def discover(portal, index, download, downloader, report):
    """Devuelve fichas, secciones y páginas ya descargadas; nunca amplía el host."""
    queue = deque([(portal.indice, 0)])
    visited = set()
    pages = {}
    candidates = []
    found_sections = {}
    depth_limited = False
    while queue and len(visited) < portal.max_paginas:
        url, depth = queue.popleft()
        if url in visited:
            continue
        if url != portal.indice:
            downloader.allowed_urls.add(url)
            try:
                page = download(url)
            except SourceBackoff:
                raise
            except (AccessError, ValueError):
                report('PAGINA_PENDIENTE', 'Página relevante inaccesible; se reintentará en otro ciclo.')
                visited.add(url)
                continue
        else:
            page = index
        visited.add(url)
        pages[url] = page
        parser = Text()
        try:
            parser.feed(page['contenido'].decode('utf-8-sig'))
            anchors = Links()
            anchors.feed(page['contenido'].decode('utf-8-sig'))
        except (UnicodeError, ValueError) as exc:
            report('PAGINA_PENDIENTE', 'HTML no interpretable; revisión pendiente.')
            continue
        found = sections(page['contenido'], portal, url)
        # La portada y los directorios se conservan como accesos, no como becas.
        if url != portal.indice and RELEVANT.search(parser.title or ''):
            if NEGATIVE.search(parser.title or ''):
                report('CANDIDATO_DESCARTADO', 'Noticia o anuncio informativo, sin ficha de beca.')
            elif CATEGORY.fullmatch(parser.title or '') or (found and len(found) > 1):
                report('CANDIDATO_DESCARTADO', 'Categoría de becas, sin convocatoria individual.')
            else:
                candidates.append(url)
        for section in found:
            if NEGATIVE.search(section.titulo):
                report('CANDIDATO_DESCARTADO', 'Sección informativa, sin ficha de beca.')
            else:
                found_sections[section.identidad] = section
                candidates.append(section.identidad)
        if depth >= portal.max_profundidad:
            if any(RELEVANT.search(label) for _, label in anchors.anchors):
                depth_limited = True
            continue
        for href, label in anchors.anchors:
            target = urljoin(url, href)
            if (admitted_url(portal, target) and target not in visited
                    and RELEVANT.search(' '.join((label, target.rsplit('/', 1)[-1].replace('-', ' '))))
                    and target not in (queued for queued, _ in queue)):
                queue.append((target, depth + 1))
    if queue or depth_limited:
        report('INDICE_LIMITE', 'Exploración parcial por límite de páginas o profundidad.')
    return list(dict.fromkeys(candidates)), found_sections, pages
