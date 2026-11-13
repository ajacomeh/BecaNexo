"""Contrato público y acotado de paginación SIAU; no evalúa JavaScript."""
import json
import re
import base64
import hashlib
from copy import deepcopy
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlencode, unquote_plus, urlsplit

from convocatorias.siau_red import ROOT, AGENT, AccessError


AJAX_INDEX = ROOT + '/wp-admin/admin-ajax.php'
MAX_INDEX_PAGES = 12
PUBLIC_TEMPLATE_KEYS = frozenset({'columns', 'exclude_items', 'ignore_items_size', 'img_size',
    'items_layout', 'items_offset', 'load_animation', 'orderby_query_args', 'overriding_link',
    'page_args', 'post_id', 'query_args', 'type', 'us_grid_ajax_index',
    'us_grid_filter_query_string', 'us_grid_index', 'us_grid_post_type'})
PUBLIC_QUERY_KEYS = frozenset({'post__not_in', 'post_status', 'post_type', 'posts_per_page',
                               'tax_query', 'paged'})
PRIVATE_MARKER = re.compile(r'token|nonce|secret|password|cookie|session|authorization|credential|bearer|jwt|api[_-]?key', re.I)
PUBLIC_SLUG = re.compile(r'[a-z0-9_-]{1,64}', re.I)


class GridConfig(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag != 'div' or 'w-grid-json' not in attrs.get('class', '').split():
            return
        raw = attrs.get('onclick', '')
        if not raw.startswith('return '):
            raise AccessError('Contrato de la cuadrícula SIAU desconocido.')
        try:
            self.values.append(json.loads(raw[7:].rstrip(';')))
        except (ValueError, TypeError) as exc:
            raise AccessError('Configuración AJAX no interpretable.') from exc


def _unsafe_value(value, depth=0):
    """Rechaza señales privadas incluso tras codificación habitual; nunca registra el valor."""
    if depth > 8:
        return True
    if isinstance(value, dict):
        return any(_unsafe_value(str(key), depth + 1) or _unsafe_value(item, depth + 1)
                   for key, item in value.items())
    if isinstance(value, list):
        return len(value) > 100 or any(_unsafe_value(item, depth + 1) for item in value)
    if value is None or type(value) in (bool, int, float):
        return False
    if not isinstance(value, str) or len(value) > 512:
        return True
    variants = {value}
    for _ in range(3):
        variants |= {unescape(unquote_plus(item)) for item in tuple(variants)}
    for item in tuple(variants):
        if PRIVATE_MARKER.search(item):
            return True
        if item.startswith(('{', '[')):
            try:
                if _unsafe_value(json.loads(item), depth + 1):
                    return True
            except (ValueError, TypeError):
                return True
        if re.fullmatch(r'[A-Za-z0-9+/]{8,}={0,2}', item) and len(item) % 4 == 0:
            try:
                decoded = base64.b64decode(item, validate=True).decode('utf-8')
            except (ValueError, UnicodeError):
                continue
            if PRIVATE_MARKER.search(decoded):
                return True
    return False


def _public_shape(config):
    if (not isinstance(config, dict)
            or set(config) != {'action', 'infinite_scroll', 'max_num_pages', 'pagination', 'template_vars'}
            or config['action'] != 'us_ajax_grid' or config['pagination'] != 'ajax'
            or type(config['max_num_pages']) is not int or not 1 <= config['max_num_pages'] <= 1000
            or type(config['infinite_scroll']) not in (bool, int)
            or config['infinite_scroll'] not in (0, 1)
            or not isinstance(config['template_vars'], dict)
            or _unsafe_value(config)):
        return False
    variables = config['template_vars']
    if not set(variables) <= PUBLIC_TEMPLATE_KEYS or variables.get('us_grid_filter_query_string') is not None:
        return False
    for key, value in variables.items():
        if key in ('query_args', 'orderby_query_args', 'page_args', 'us_grid_filter_query_string'):
            continue
        if key == 'overriding_link':
            try:
                if json.loads(value) != {'url': ''}:
                    return False
            except (TypeError, ValueError):
                return False
            continue
        if key in ('ignore_items_size', 'post_id', 'us_grid_ajax_index', 'us_grid_index'):
            if type(value) is not int or not 0 <= value <= 1000000000:
                return False
        elif not isinstance(value, str) or not PUBLIC_SLUG.fullmatch(value):
            return False
    order = variables.get('orderby_query_args')
    if order is not None and (not isinstance(order, dict) or set(order) != {'orderby'}
                              or not isinstance(order['orderby'], dict)
                              or set(order['orderby']) != {'date'}
                              or order['orderby']['date'] not in ('ASC', 'DESC', 'asc', 'desc')):
        return False
    page = variables.get('page_args')
    if page is not None and (not isinstance(page, dict) or set(page) != {'page_type', 'post_ID'}
                            or page['page_type'] not in ('post', 'page')
                            or type(page['post_ID']) is not int or not 0 <= page['post_ID'] <= 1000000000):
        return False
    query = variables.get('query_args')
    if not isinstance(query, dict) or not set(query) <= PUBLIC_QUERY_KEYS:
        return False
    taxes = query.get('tax_query')
    if (query.get('post_type') != ['post']
            or query.get('post_status', ['publish']) not in (['publish'], ['publish', 'acf-disabled'])
            or not str(query.get('posts_per_page', 200)).isdecimal()
            or not 1 <= int(query.get('posts_per_page', 200)) <= 200
            or (query.get('paged') is not None and (type(query['paged']) is not int or not 1 <= query['paged'] <= 12))
            or not isinstance(query.get('post__not_in', []), list)
            or any(type(item) is not int or not 0 <= item <= 1000000000 for item in query.get('post__not_in', []))
            or not isinstance(taxes, list) or not 1 <= len(taxes) <= 8):
        return False
    for item in taxes:
        if (not isinstance(item, dict) or set(item) != {'field', 'taxonomy', 'terms'}
                or item['field'] != 'slug' or item['taxonomy'] not in ('category', 'nivel', 'modalidad', 'idioma')
                or not isinstance(item['terms'], list) or not 1 <= len(item['terms']) <= 50
                or any(not isinstance(term, str) or not PUBLIC_SLUG.fullmatch(term) for term in item['terms'])):
            return False
    return any(item['taxonomy'] == 'category' and item['terms'] == ['convocatorias'] for item in taxes)


def grid_config(content):
    try:
        parser = GridConfig()
        parser.feed(content.decode('utf-8-sig'))
    except (UnicodeError, ValueError) as exc:
        raise AccessError('Índice nacional no interpretable.') from exc
    if len(parser.values) != 1:
        raise AccessError('Se esperaba una única cuadrícula nacional.')
    config = parser.values[0]
    if not _public_shape(config):
        raise AccessError('La cuadrícula ya no consulta convocatorias públicas.')
    return config


def ajax_request(config, page):
    if not _public_shape(config):
        raise AccessError('Configuración AJAX fuera del contrato público.')
    if type(page) is not int or not 2 <= page <= min(config['max_num_pages'], MAX_INDEX_PAGES):
        raise AccessError('Página AJAX fuera del límite aprobado.')
    variables = deepcopy(config['template_vars'])
    variables['query_args']['paged'] = page
    form = {key: ('true' if value is True else 'false' if value is False else str(value))
            for key, value in config.items() if key != 'template_vars'}
    form['template_vars'] = json.dumps(variables, ensure_ascii=False, separators=(',', ':'))
    body = urlencode(form).encode('utf-8')
    if len(body) > 32768:
        raise AccessError('Solicitud AJAX excede 32 KiB.')
    query = variables['query_args']
    return body, {'accion': 'us_ajax_grid', 'pagina': page,
                  'max_paginas_anunciadas': config['max_num_pages'],
                  'solicitud_sha256': hashlib.sha256(body).hexdigest(),
                  'parametros': {'pagination': 'ajax', 'infinite_scroll': bool(config['infinite_scroll']),
                                 'post_type': ['post'], 'post_status': query.get('post_status', ['publish']),
                                 'posts_per_page': int(query.get('posts_per_page', 200)),
                                 'taxonomias': [{'taxonomy': item['taxonomy'], 'terms': item['terms']}
                                                for item in query['tax_query']]}}


def robots_allowed(content, url, agent=AGENT, root=ROOT):
    """Reglas de mayor especificidad RFC 9309; entradas ambiguas cierran acceso."""
    if not url.startswith(root + '/'):
        return False
    try:
        lines = [line.split('#', 1)[0].strip() for line in content.decode('utf-8-sig').splitlines()]
    except UnicodeError:
        return False
    groups, agents, rules = [], [], []
    for line in lines + ['']:
        if not line:
            if agents:
                groups.append((agents, rules))
            agents, rules = [], []
            continue
        key, separator, value = line.partition(':')
        if not separator:
            return False
        key, value = key.strip().casefold(), value.strip()
        if key == 'user-agent':
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.casefold())
        elif key in ('allow', 'disallow'):
            if not agents or (value and not value.startswith('/')):
                return False
            if value:
                rules.append((key == 'allow', value))
        elif key not in ('sitemap', 'crawl-delay', 'host'):
            return False
    product = agent.split('/', 1)[0].casefold()
    specificity = max((len(name) for agents, _ in groups for name in agents
                       if name != '*' and name in product), default=0)
    relevant = [rules for agents, rules in groups if
                (any(name != '*' and len(name) == specificity and name in product for name in agents)
                 if specificity else '*' in agents)]
    if not relevant:
        return False
    path = urlsplit(url).path
    matches = []
    for group in relevant:
        for allow, rule in group:
            try:
                pattern = re.escape(rule).replace(r'\*', '.*')
                if pattern.endswith(r'\$'):
                    pattern = pattern[:-2] + '$'
                if re.match(pattern, path):
                    matches.append((len(rule.replace('*', '').rstrip('$').encode('utf-8')), allow))
            except (re.error, UnicodeError):
                return False
    return max(matches)[1] if matches else True


def robots_allow_ajax(content):
    return robots_allowed(content, AJAX_INDEX)
