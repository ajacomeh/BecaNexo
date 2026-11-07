"""Descarga pública acotada: no cookies, proxies, autenticación ni navegación libre."""
import http.client
import ipaddress
import socket
import ssl
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin

HOST = 'siau.senescyt.gob.ec'
ROOT = f'https://{HOST}'
PAGES = [ROOT + '/programa-de-becas-nacionales-jovenes-del-nuevo-ecuador-2026/',
         ROOT + '/programa-de-becas-nacionales-de-posgrado-ecuador-productivo/']
PDFS = [ROOT + '/wp-content/uploads/2026/07/bn_aa_jdne2026_bases_rf.pdf',
        ROOT + '/wp-content/uploads/2026/10/bn_4to_nivel_2026_13102026_vf-1.pdf']
ROBOTS = ROOT + '/robots.txt'
INDEX = ROOT + '/convocatorias/'
ALLOWED = frozenset([ROBOTS, INDEX, *PAGES, *PDFS])
AGENT = 'BecaNexoPreview/0.1 (academic research; bounded public preview)'


class AccessError(Exception):
    pass


def validate_url(url, allowed_urls=ALLOWED):
    if not isinstance(url, str) or url not in allowed_urls:
        raise AccessError('URL fuera de la lista cerrada HTTPS permitida.')
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.hostname != HOST
            or parts.username or parts.password or parts.port not in (None, 443)
            or parts.query or parts.fragment):
        raise AccessError('URL fuera de la lista cerrada HTTPS permitida.')
    return parts


def public_address(host):
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise AccessError('DNS sin direcciones.')
    # Rechaza incluso conjuntos mixtos. Se fija la dirección comprobada al
    # socket para no resolver otra IP entre validación y conexión (rebinding).
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global or ip.is_multicast:
            raise AccessError('DNS apunta a una dirección no pública.')
    return addresses[0][4][0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


class Downloader:
    def __init__(self, pause=2, timeout=15, total_timeout=45, allowed_urls=None):
        self.pause, self.timeout, self.total_timeout = pause, timeout, total_timeout
        self.allowed_urls = set(ALLOWED if allowed_urls is None else allowed_urls)
        self.last = None
        self.history = []
        self.current_record = None

    def once(self, url):
        parts = validate_url(url, self.allowed_urls)
        address = public_address(parts.hostname)
        conn = PinnedHTTPS(parts.hostname, address, self.timeout)
        waited = 0
        if self.last is not None:
            waiting_since = time.monotonic()
            time.sleep(max(0, self.pause - (waiting_since - self.last)))
            waited = time.monotonic() - waiting_since
        self.last = time.monotonic()
        if self.current_record is not None:
            self.current_record['inicio_peticion_utc'] = datetime.now(timezone.utc).isoformat()
            self.current_record['inicio_peticion_monotonic'] = self.last
            self.current_record['espera_ms'] = max(0, int(waited * 1000))
        limit = 8 * 1024 * 1024 if url in PDFS or url.lower().endswith('.pdf') else 2 * 1024 * 1024
        started = time.monotonic()
        try:
            conn.request('GET', parts.path, headers={'User-Agent': AGENT, 'Accept-Encoding': 'identity', 'Accept': 'text/html,application/pdf,text/plain'})
            response = conn.getresponse()
            headers = dict((k.lower(), v) for k, v in response.getheaders())
            if headers.get('content-encoding', 'identity') != 'identity':
                raise AccessError('Codificación comprimida no admitida en esta etapa.')
            if int(headers.get('content-length', '0')) > limit:
                raise AccessError('Contenido excede límite de tamaño.')
            chunks, size = [], 0
            while True:
                if time.monotonic() - started > self.total_timeout:
                    raise AccessError('Tiempo total de lectura excedido.')
                block = response.read1(min(65536, limit - size + 1))
                if not block:
                    break
                size += len(block)
                if size > limit:
                    raise AccessError('Contenido excede límite de tamaño.')
                chunks.append(block)
            return response.status, headers, b''.join(chunks)
        finally:
            conn.close()

    def fetch(self, url, can_fetch=lambda url: True):
        initial = url
        for redirect in range(3):
            validate_url(url, self.allowed_urls)
            if not can_fetch(url):
                raise AccessError('robots.txt impide o no permite confirmar este acceso.')
            for attempt in range(2):
                record = {'url': url, 'consulta_utc': datetime.now(timezone.utc).isoformat(), 'intento': attempt + 1}
                self.history.append(record)
                self.current_record = record
                try:
                    status, headers, body = self.once(url)
                    record['http'] = status
                except AccessError as exc:
                    record['error'] = str(exc)
                    raise
                except (OSError, http.client.HTTPException, ValueError) as exc:
                    record['error'] = type(exc).__name__
                    if isinstance(exc, ssl.SSLError) or attempt == 1:
                        raise AccessError('Error de conexión: ' + type(exc).__name__) from exc
                    continue
                if status in (502, 503, 504) and attempt == 0:
                    continue
                break
            if status in (301, 302, 303, 307, 308):
                try:
                    url = urljoin(url, headers.get('location', ''))
                except ValueError as exc:
                    raise AccessError('Redirección mal formada.') from exc
                validate_url(url, self.allowed_urls)
                if redirect == 2:
                    raise AccessError('Demasiadas redirecciones.')
                continue
            if status != 200:
                raise AccessError(f'HTTP {status}; no se elude la respuesta del servidor.')
            return {'url_solicitada': initial, 'url': url, 'consulta_utc': record.get('inicio_peticion_utc', record['consulta_utc']),
                    'content_type': headers.get('content-type', ''), 'contenido': body}
        raise AccessError('Redirección no resuelta.')
