"""Candidatas del índice SIAU; no decide admisibilidad ni publica becas."""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from convocatorias.siau_red import HOST, INDEX

MAX_FICHAS = 12
MAX_BASES = 24
FICHA = re.compile(r'/programa-de-becas-nacionales-[a-z0-9-]+/')
BASE = re.compile(r'/wp-content/uploads/\d{4}/\d{2}/[a-zA-Z0-9._-]+\.pdf')


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
