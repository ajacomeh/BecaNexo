# Modelo vigente para comparación v0.6 — 26/10/2026

La base histórica Modelo_logico_v05.json y Modelo_ER.mmd se conservan para trazabilidad. El modelo actualizado completo es Modelo_logico_v06.json; este suplemento define sus cambios respecto al ER v05. No cambia TRA_RECOMENDACION ni TRA_EVALUACION_REQUISITO: siguen sin implementarse.

MAE_REQUISITO añade:

| Campo | Tipo | Regla |
| --- | --- | --- |
| destino_id | FK CAT_PAIS, nullable | Requiere opcion_estudio_id y país dentro de REL_OPCION_ESTUDIO_PAIS de esa opción. NULL mantiene ámbito común/opción. |
| relacion_formacion | varchar(20), no null | pendiente (inicial), independiente, misma_formacion. Solo condiciones académicas usan las dos últimas. |
| grupo_formacion | varchar(64), nullable | Obligatorio solo en misma_formacion; clave local a la convocatoria, letras ASCII, números, guion/subrayado. Sus miembros tienen igual obligatoriedad. |
| equivalencias | jsonb, no null, inicial [] | Filas tipo/origen/admitido/referencia/pais/provincia. Contrato cerrado; procedencia obligatoria, no texto ejecutable. |

PostgreSQL comprueba coherencia grupo/relación y destino/opción; las FK mantienen integridad referencial. El servidor comprueba pertenencia de opción/país, ámbito académico, equivalencias y obligatoriedad del grupo bajo el lock de convocatoria. La publicación revalida las reglas. No se permite retirar de una opción un país referenciado por un requisito, aun inactivo.

Los campos JSON de una equivalencia tienen tipos string, salvo pais/provincia que pueden ser null si no aplican. Título: pais/provincia nulos. Provincia: país admitido, provincia nula. Ciudad: país y provincia admitidos. Origen se normaliza con Unicode NFC, espacios y mayúsculas; se exige destino admitido y referencia no vacía. No se encadenan equivalencias; orígenes repetidos en un mismo contexto se rechazan. Para nombres territoriales literales, contexto inequívoco de un país y, para ciudad, una provincia. Si hay varios contextos posibles se requiere equivalencia contextual explícita (puede relacionar nombres iguales).

Contratos CAT_TIPO_REQUISITO: FORMACION v2 añade niveles_admitidos (lista del dominio vigente), conserva nivel_minimo opcional como dato original no suficiente para comparar. Debe existir lista o mínimo original. EXPERIENCIA v2 añade convencion_documentada opcional. Los demás mantienen versión 1; se amplía la evaluación sin reescribir valor_estructurado.

Migración 0002: cuatro AddField y dos CHECK, sin RunPython ni cambio de filas antiguas a una interpretación nueva. Valores iniciales null, [], pendiente preservan incertidumbre. La carga de catálogos actualiza definiciones de contrato, nunca JSON de requisitos ni perfil. Fórmulas de promedio y convenciones ejecutables de meses siguen pendientes de evidencia concreta aprobada.
