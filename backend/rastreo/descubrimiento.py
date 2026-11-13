"""Candidatas del índice SIAU; no decide admisibilidad ni publica becas."""
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from convocatorias.siau_red import HOST, INDEX, NATIONAL_INDEX
from convocatorias.siau_extraccion import FichaHTML

MAX_FICHAS = 12
MAX_BASES = 24
FICHA = re.compile(r'/programa-de-becas-nacionales-[a-z0-9-]+/')
BASE = re.compile(r'/wp-content/uploads/\d{4}/\d{2}/[a-zA-Z0-9._-]+\.pdf')
NATIONAL_FICHA = re.compile(r'/[a-z0-9]+(?:-[a-z0-9]+)+/')


def candidate_url(raw, pattern):
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        url = urljoin(INDEX, raw.strip())
        parts = urlsplit(url)
        invalid = (parts.scheme != 'https' or parts.hostname != HOST or parts.port not in (None, 443)
                   or parts.username or parts.password or parts.query or parts.fragment
                   or not pattern.fullmatch(parts.path) or len(url.encode('utf-8')) > 2048)
    except ValueError:
        return None
    if invalid:
        return None
    return f'https://{HOST}{parts.path}'


class IndexLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href')
            url = candidate_url(href, FICHA)
            if url:
                self.urls.add(url)


def index_pages(content):
    parser = IndexLinks()
    parser.feed(content.decode('utf-8-sig'))
    pages = sorted(parser.urls)
    return pages[:MAX_FICHAS], len(pages) > MAX_FICHAS


def national_title(title):
    name = ' '.join(title.casefold().split())
    return bool(re.search(r'\bbecas? nacionales?\b', name)) and 'internacional' not in name


class NationalIndexLinks(HTMLParser):
    """Solo tarjetas de convocatorias del índice, no menús ni imágenes enlazadas."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []
        self.article = False
        self.article_count = 0
        self.title = False
        self.href = None
        self.words = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if tag == 'article':
            self.article = 'category-convocatorias' in classes
            if self.article:
                self.article_count += 1
        elif self.article and tag == 'h2' and 'entry-title' in classes:
            self.title = True
        elif self.title and tag == 'a':
            self.href = attrs.get('href')
            self.words = []

    def handle_data(self, data):
        if self.href is not None:
            self.words.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None:
            url = candidate_url(self.href, NATIONAL_FICHA)
            if url and national_title(''.join(self.words)) and url not in self.urls:
                self.urls.append(url)
            self.href = None
        elif tag == 'h2':
            self.title = False
        elif tag == 'article':
            self.article = False


def national_index_pages(content):
    parser = NationalIndexLinks()
    page = content.decode('utf-8-sig')
    parser.feed(page)
    # El portal usa desplazamiento infinito mediante AJAX. No se simula su
    # POST ni se afirma cobertura total cuando anuncia más páginas.
    match = re.search(r'"max_num_pages"\s*:\s*(\d+)', unescape(page))
    more_pages = match is None or int(match[1]) > 1
    return parser.urls[:MAX_FICHAS], more_pages or len(parser.urls) > MAX_FICHAS


def national_ficha_content(content):
    """Confirma estructura de ficha antes de crear identidad persistente."""
    parser = FichaHTML()
    try:
        parser.feed(content.decode('utf-8-sig'))
    except UnicodeError:
        return False
    parser.flush()
    lines = parser.lines
    return (bool(lines) and national_title(lines[0])
            and any('POSTULA HASTA' in line.upper() for line in lines)
            and any('REQUISITOS GENERALES' in line.upper() for line in lines))
