"""Retipificación de requisitos creados por el llenado automático, con el extractor vigente.

Solo propone un cambio cuando la cláusula, interpretada de nuevo, recibe un tipo distinto y su contrato
se valida con los valores escritos en el propio texto (o es una condición externa con su texto literal).
Nunca invierte negaciones, nunca deduce valores y nunca convierte lo externo en dato comparable.
"""
from convocatorias.models import TipoRequisito
from convocatorias.reglas import CONTRATOS, EXTERNOS
from .estructura_semantica import interpretar_requisitos


def propuesta(requisito):
    """{'codigo', 'valor', 'modo'} con la tipificación vigente de su texto, o None si no cambia o no es segura."""
    candidatos = interpretar_requisitos(requisito.texto_original or '', version_id=None, url=None)
    if len(candidatos) != 1:
        return None   # El texto se divide en varias cláusulas: no se reparte un registro existente.
    candidato = candidatos[0]
    codigo = candidato['tipo_sugerido']
    if candidato['estado'] == 'externa' and codigo in EXTERNOS:
        valor, modo = {'descripcion': requisito.texto_original}, 'entidad_oferente'
    elif candidato['estado'] == 'identificada' and codigo in CONTRATOS and codigo not in EXTERNOS:
        valor, modo = candidato['valor_sugerido'], 'dato_declarado'
    else:
        return None
    if codigo == requisito.tipo_requisito.codigo:
        return None
    return {'codigo': codigo, 'valor': valor, 'modo': modo, 'metodo': candidato['metodo']}


def aplicar(requisito, cambio, convocatoria):
    """Valida el nuevo tipo con el serializer del catálogo y lo guarda; devuelve el error o None."""
    from convocatorias.serializers import RequisitoSerializer
    tipo = TipoRequisito.objects.filter(codigo=cambio['codigo']).first()
    if tipo is None:
        return f"El tipo {cambio['codigo']} no está en el catálogo; ejecuta la carga de catálogos."
    serializer = RequisitoSerializer(requisito, data={'tipo_requisito': tipo.pk, 'valor_estructurado': cambio['valor'],
                                                      'modo_comprobacion': cambio['modo'], 'operador': CONTRATOS[cambio['codigo']][1]},
                                     partial=True, context={'convocatoria': convocatoria})
    if not serializer.is_valid():
        return f'El contrato del tipo {cambio["codigo"]} no se cumple con los valores escritos: {serializer.errors}'
    serializer.save()
    return None
