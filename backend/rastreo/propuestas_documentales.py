"""Propuestas editoriales desde evidencia archivada; nunca escribe convocatorias."""
import re
import unicodedata


def _normal(value):
    return ''.join(char for char in unicodedata.normalize('NFD', value.casefold())
                   if unicodedata.category(char) != 'Mn')


def proponer(evidencia_tabular, evidencia_pdf):
    propuestas = []
    vistos = set()

    def agregar(texto, tipo, condicion, procedencia, *, categoria=None, seccion=None,
                fecha=None, porcentajes=(), enlace=None):
        texto = ' '.join(str(texto or '').split())[:350]
        if not texto or len(propuestas) >= 80:
            return
        normal = _normal(texto)
        advertencias = []
        if categoria:
            advertencias.append('Pertenece a una categoría específica; confirma su ámbito.')
        if seccion and re.search(r'\bespecific', _normal(seccion)):
            advertencias.append('La sección declara condiciones específicas; confirma su ámbito.')
        if condicion != 'inicial_por_revisar':
            advertencias.append('Condición alternativa o de renovación; no tratar como requisito acumulativo.')
        if len(porcentajes) > 1 or re.search(r'\b(?:hasta|entre|variable|segun evaluacion|al\s+\d+\s*%)\b', normal):
            advertencias.append('Cobertura variable; no asignar porcentaje fijo.')
        destino = None
        campo = None
        valor = None
        if tipo in ('requisito', 'requisito_o_documento', 'documento_exigido'):
            campo = 'requisito' if tipo == 'requisito' else 'documento exigido'
            destino = 'requisitos'
            valor = texto
            if categoria or condicion != 'inicial_por_revisar' or (seccion and re.search(r'\bespecific', _normal(seccion))):
                destino = None
        elif tipo == 'beneficio':
            campo, valor = 'beneficio', texto
            if not categoria and condicion == 'inicial_por_revisar' and not (seccion and re.search(r'\bespecific', _normal(seccion))):
                destino = 'beneficios'
        elif tipo == 'cronograma':
            campo, valor = 'fecha o cronograma', texto
            # Solo el cierre de postulaciones del programa general puede ser un cierre global.
            if (fecha and not categoria and condicion == 'inicial_por_revisar'
                    and len(re.findall(r'\b\d{1,2}/\d{1,2}/20\d{2}\b', texto)) == 1
                    and re.search(r'\b(?:cierre|fin|plazo)\s+(?:de\s+)?(?:las\s+)?postulaciones\b', normal)
                    and not re.search(r'\b(?:cuotas|aprobacion|notificacion|inicio de clases|curso)\b', normal)):
                destino, campo, valor = 'general', 'cierre_dia', fecha
        elif tipo in ('programa', 'programa_o_nivel'):
            campo, valor = 'programa o nivel', texto
            advertencias.append('Confirma nivel, modalidad, destino y elegibilidad antes de crear una opción.')
        elif tipo == 'modalidad':
            campo, valor = 'modalidad', texto
            advertencias.append('Confirma a qué programa corresponde esta modalidad.')
        elif tipo == 'oferente_mencionado':
            campo, valor = 'entidad mencionada', texto
            advertencias.append('Confirma que sea oferente ecuatoriano, no solo difusor.')
        elif tipo in ('postulacion', 'enlace_documental'):
            campo, valor = 'enlace oficial', enlace or texto
            if tipo == 'enlace_documental' and enlace and re.search(r'\b(?:bases?|reglamento)\b', normal):
                destino, campo, valor = 'general', 'url_bases', enlace
            elif enlace:
                advertencias.append('Distingue ficha, registro y formulario directo antes de asignar el enlace.')
        if campo is None:
            return
        key = (campo, valor, procedencia.get('documento_id'), procedencia.get('pagina'),
               procedencia.get('fila'))
        if key in vistos:
            return
        vistos.add(key)
        propuestas.append({'campo': campo, 'valor': valor, 'texto_original': texto,
                          'destino': destino, 'estado': 'pendiente_revision',
                          'advertencias': advertencias, 'categoria': categoria,
                          'seccion': seccion, 'condicion': condicion,
                          'procedencia': procedencia})

    for table in evidencia_tabular.get('tablas', []):
        section = ' · '.join(filter(None, (table.get('encabezado'), table.get('titulo'))))
        category = section if re.search(r'\bbeca\s+(?:por|de|socioeconomica|deportiva|solidaridad)\b|\b(?:solidaridad|excelencia|discapacidad|deportiva|artistica|filiacion|representacion|minoritari)\b', _normal(section)) else None
        alternatives = False
        for index, row in enumerate(table['filas'], 1):
            if index == 1 and all(_normal(cell) in ('proceso', 'fecha', 'requisito', 'beneficio') for cell in row['celdas']):
                continue
            text = ' · '.join(row['celdas'])
            if row['condicion'] == 'alternativa_por_revisar' or re.search(r'\b(?:una de las siguientes|cualquiera de|alternativas?|o bien)\b', _normal(text)):
                alternatives = True
            condition = ('alternativa_por_revisar' if alternatives and row['condicion'] == 'inicial_por_revisar'
                         else row['condicion'])
            if row['tipo'] == 'sin_clasificar':
                continue
            agregar(text, row['tipo'], condition, {**table['procedencia'], 'seccion': section, 'fila': index},
                   categoria=category, seccion=section, fecha=row.get('fecha_sugerida'),
                   porcentajes=row.get('porcentajes_literales') or [])
    for link in evidencia_tabular.get('enlaces_documentales', []):
        agregar(link['texto'], 'enlace_documental', 'inicial_por_revisar',
               {**link['procedencia'], 'seccion': 'Enlaces documentales'},
               seccion='Enlaces documentales', enlace=link['url'])
    for document in evidencia_pdf.get('documentos', []):
        for item in document.get('fragmentos', []):
            agregar(item['texto_original'], item['tipo'], item['condicion'], item['procedencia'],
                   categoria=item.get('categoria'), seccion=item.get('seccion'),
                   fecha=item.get('fecha_sugerida'), porcentajes=item.get('porcentajes_literales') or [],
                   enlace=(item.get('enlaces_literales') or [None])[0])
    return propuestas
