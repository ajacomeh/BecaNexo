import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from convocatorias.siau_bases import annotate_pdf, compare_pdf
from convocatorias.siau_extraccion import extract_html, validate_observation
from convocatorias.siau_red import AGENT, INDEX, PAGES, PDFS, ROBOTS, AccessError, Downloader


def write_reports(directory, report):
    (directory / 'informe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    # Texto plano: nunca renderizar HTML descargado en una interfaz confiable.
    text = ['SIAU — VISTA PREVIA SIN PERSISTENCIA DE NEGOCIO',
            'Ejecución de red real. No es autorización de publicación.',
            'Consulta UTC: ' + report['inicio_utc'], 'Estado: ' + report['estado'],
            'Incidencias: ' + json.dumps(report['incidencias'], ensure_ascii=False)]
    for item in report['fichas']:
        text.extend(['\n' + item['titulo']['texto_original'], item['url'],
                     'SHA-256: ' + item['sha256'], 'Vigencia observada: ' + item['vigencia_observada'],
                     '\nTEXTO ORIGINAL DE LA FICHA\n' + item['texto_ficha'],
                     '\nDATOS, EVIDENCIA Y ADVERTENCIAS\n' + json.dumps({k: v for k, v in item.items() if k != 'texto_ficha'}, ensure_ascii=False, indent=2)])
    text.append('\nDESCARGAS E HISTORIAL\n' + json.dumps(report['descargas'], ensure_ascii=False, indent=2))
    text.append(json.dumps(report['accesos'], ensure_ascii=False, indent=2))
    (directory / 'informe.txt').write_text('\n'.join(text), encoding='utf-8')


class Command(BaseCommand):
    help = 'Descarga exclusivamente dos fichas SIAU y sus bases conocidas. Solo archivos locales, sin ORM.'
    # Sin checks automáticos ni comprobación de migraciones que puedan abrir BD.
    requires_system_checks = []

    def handle(self, *args, **options):
        root = Path(settings.BASE_DIR).parent / 'outputs' / 'rastreo'
        now = datetime.now(timezone.utc)
        directory = root / now.strftime('%Y%m%dT%H%M%S%fZ')
        directory.mkdir(parents=True, exist_ok=False)
        downloader = Downloader()
        report = {'version_contrato': 1, 'modo': 'red_real_sin_escrituras_BD',
                  'inicio_utc': now.isoformat(), 'fecha_referencia_ecuador': now.astimezone(ZoneInfo('America/Guayaquil')).date().isoformat(),
                  'estado': 'completa_con_revision_manual_pendiente', 'fichas': [],
                  'descargas': [], 'incidencias': [], 'accesos': downloader.history}
        def download(url, name, allowed=lambda url: True):
            result = downloader.fetch(url, can_fetch=allowed)
            content = result['contenido']
            mime = result['content_type'].split(';')[0].lower().strip()
            expected = 'application/pdf' if url in PDFS else ('text/plain' if url == ROBOTS else 'text/html')
            if mime != expected or (url in PDFS and not content.startswith(b'%PDF-')):
                raise AccessError('Contenido distinto del tipo esperado; no se interpreta.')
            (directory / name).write_bytes(content)
            report['descargas'].append({k: v for k, v in result.items() if k != 'contenido'} | {
                'archivo': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
            return result
        try:
            robots = download(ROBOTS, 'robots.txt')
            policy = RobotFileParser(ROBOTS)
            policy.parse(robots['contenido'].decode('utf-8-sig').splitlines())
            downloader.pause = max(downloader.pause, policy.crawl_delay(AGENT) or 0)
            can_fetch = lambda url: policy.can_fetch(AGENT, url)
            bases = {}
            # Inspección de entrada; no se siguen los enlaces del índice.
            try:
                download(INDEX, 'portal.html', can_fetch)
            except AccessError as exc:
                report['incidencias'].append({'url': INDEX, 'error': str(exc)})
            for index, url in enumerate(PAGES, 1):
                try:
                    page = download(url, f'ficha-{index}.html', can_fetch)
                    item = validate_observation(extract_html(page), now.astimezone(ZoneInfo('America/Guayaquil')).date())
                    report['fichas'].append(item)
                    item['bases'] = []
                    linked = set()
                    for link_index, link in enumerate(item['enlaces_bases'], 1):
                        if link['url'] in linked:
                            continue
                        linked.add(link['url'])
                        try:
                            if link['url'] not in PDFS:
                                raise AccessError('Base fuera de la lista cerrada; requiere inspección y autorización de URL.')
                            if link['url'] not in bases:
                                filename = f'base-{index}-{link_index}.pdf'
                                pdf = download(link['url'], filename, can_fetch)
                                bases[link['url']] = annotate_pdf(pdf['url'], hashlib.sha256(pdf['contenido']).hexdigest()) | {
                                    'archivo_original_completo': filename, 'url': pdf['url'],
                                    'sha256': hashlib.sha256(pdf['contenido']).hexdigest(),
                                    'consulta_utc': pdf['consulta_utc'],
                                }
                            review = bases[link['url']]
                            item['bases'].append(review)
                            compare_pdf(item, review)
                        except AccessError as exc:
                            report['incidencias'].append({'url': link['url'], 'error': str(exc)})
                            item['advertencias'].append('Base no recuperada: revisión manual pendiente.')
                except (AccessError, ValueError) as exc:
                    report['incidencias'].append({'url': url, 'error': str(exc)})
            if report['incidencias']:
                report['estado'] = 'parcial' if report['fichas'] else 'fallida'
            elif any(not item['descripcion']['texto_original'] or not item['requisitos']['texto_original'] or not item['seccion_completa'] for item in report['fichas']):
                report['estado'] = 'estructura_inesperada'
        except (AccessError, ValueError) as exc:
            report['estado'] = 'fallida'
            report['incidencias'].append({'url': ROBOTS, 'error': str(exc), 'decision': 'Sin robots verificable, no continuar.'})
        finally:
            report['fin_utc'] = datetime.now(timezone.utc).isoformat()
            write_reports(directory, report)
        self.stdout.write(str(directory / 'informe.txt'))
        self.stdout.write(str(directory / 'informe.json'))
        self.stdout.write('Estado: ' + report['estado'] + '. Fichas: ' + str(len(report['fichas'])) + '. Sin escrituras de negocio.')
        if report['estado'] in {'fallida', 'parcial', 'estructura_inesperada'}:
            raise CommandError('Vista previa incompleta; consultar incidencias en el informe local.')
