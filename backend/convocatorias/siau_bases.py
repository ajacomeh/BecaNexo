"""Notas de inspección humana del 26/10/2026, NO extracción automática PDF.

Solo se adjuntan si coincide URL y SHA-256 del PDF realmente descargado.
El documento original completo sigue siendo la evidencia; estas notas no
transcriben todas sus tablas ni habilitan publicación o reglas ejecutables.
"""
from copy import deepcopy
from .siau_red import PDFS

REVIEWS = {
    PDFS[0]: {
        'sha256': 'f1f52296aa6a5896d02aba2dd731ce49ec04415efe011578af68daea775ec2c3',
        'paginas': 9,
        'cierre': {'original': '28 de junio de 2026', 'fecha': '2026-06-28', 'pagina': 4},
        'apertura': {'original': '4 de junio de 2026', 'fecha': '2026-06-04', 'pagina': 4},
        'beneficio': {'pagina': 2, 'original': 'USD 828.97', 'moneda': 'USD', 'monto': '828.97',
                      'concepto': 'Manutención', 'periodicidad': 'Una sola vez; un período académico en 2026'},
        'notas': ['P. 1: técnico superior, tecnológico superior, tecnológico superior universitario y grado; todas las modalidades.',
                  'P. 1: pie de reforma menciona comité MINEDEC; p. 8, difusión/contacto del Ministerio de Educación, Deporte y Cultura. Validar su función oferente antes de registrar entidad.',
                  'P. 2–3: requisitos, documentos e interoperabilidad; grupos de acción afirmativa y vulnerabilidad. Revisión manual completa pendiente.',
                  'P. 2: aprobación del 60 % de malla del período financiado para liquidación/finiquito; no transformarla en requisito de ingreso.',
                  'P. 9: formato de certificado de estudios. Documento verificado externamente.'],
    },
    PDFS[1]: {
        'sha256': 'b04ae4b7dd597bee88b46e7fc8023d1c2adde6b389c8282f79add5a53c004afd',
        'paginas': 10,
        'cierre': {'original': '25 de octubre de 2026', 'fecha': '2026-10-25', 'pagina': 4},
        'apertura': {'original': '15 de octubre de 2026', 'fecha': '2026-10-15', 'pagina': 4},
        'beneficio': {'pagina': 2, 'original': '100% del costo de matrícula y aranceles hasta un valor de $3000',
                      'moneda': None, 'tope_literal': '$3000', 'porcentaje': '100%', 'concepto': 'Matrícula y aranceles'},
        'notas': ['P. 1: programa del Ministerio de Educación, Deporte y Cultura – MINEDEC, según objetivo explícito.',
                  'P. 1–2: 39 campos detallados priorizados; no sustituir por cualquier área de catálogo.',
                  'P. 2: especialización, maestría académica y maestría tecnológica, en línea; período completo.',
                  'P. 2: diferencia sobre el tope a cargo de la persona becaria; $ no identifica por sí solo código ISO.',
                  'P. 2–4: requisitos/documentación, interoperabilidad y excepciones requieren revisión manual completa.',
                  'P. 5: promedios para puntuación de priorización, no mínimos generales de elegibilidad.',
                  'P. 6: adjudicación/contratos tienen otras fechas; no son el cierre de postulación.'],
    },
}


def annotate_pdf(url, sha256):
    review = REVIEWS.get(url)
    if not review or review['sha256'] != sha256:
        return {'estado': 'revision_manual_pendiente', 'notas': ['PDF nuevo o modificado: no reutilizar anotaciones de otra versión.']}
    return {**deepcopy(review), 'estado': 'inspeccion_manual_parcial', 'fecha_inspeccion': '2026-10-26',
            'url': url, 'advertencia': 'No se extrae automáticamente texto PDF. Consultar documento completo; requisitos y tablas pendientes de revisión.'}


def compare_pdf(item, review):
    if review.get('estado') != 'inspeccion_manual_parcial':
        return
    html_date, pdf_date = item['cierre']['fecha'], review['cierre']['fecha']
    item.setdefault('comparaciones_bases', []).append({
        'campo': 'cierre', 'html': item['cierre'],
        'pdf': {**review['cierre'], 'url': review['url'], 'precision': 'dia', 'hora': None, 'zona_horaria': None},
        'resultado': 'coincide' if html_date == pdf_date else 'diferencia_para_revision',
    })
    if html_date != pdf_date:
        item['advertencias'].append('Cierre HTML/PDF diferente o incompleto: conservar ambas evidencias sin elegir una.')
    html_benefit, pdf_benefit = item['beneficio'], review['beneficio']
    if 'tope_literal' in pdf_benefit:
        matches = (pdf_benefit['porcentaje'] in html_benefit['porcentajes'] and
                   any(amount['original'] == pdf_benefit['tope_literal'] and amount['tipo'] == 'tope'
                       for amount in html_benefit['cantidades']))
    else:
        matches = any(amount['valor_literal'] == pdf_benefit['monto'] and amount['moneda'] == pdf_benefit['moneda']
                      and amount['tipo'] == 'monto_mencionado' for amount in html_benefit['cantidades'])
    item['comparaciones_bases'].append({
        'campo': 'cifras_de_cobertura', 'html': html_benefit,
        'pdf': {**pdf_benefit, 'url': review['url']},
        'resultado': 'cifras_coinciden_revisar_condiciones' if matches else 'diferencia_para_revision',
    })
    if not matches:
        item['advertencias'].append('Cifras de cobertura HTML/PDF diferentes o incompletas; revisar ambas, sin sustituirlas.')
    item['advertencias'].append('Las bases contienen condiciones adicionales; la ficha HTML no sustituye su lectura completa.')
