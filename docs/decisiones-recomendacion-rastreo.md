# Decisiones aprobadas para la segunda entrega

## Revisión administrativa implementada — 29/10/2026

Se habilita registrar decisiones independientes sobre extracción, documentación y oferente en una versión exacta. Se reutiliza AUD_REVISION_RASTREO y se conserva su inmutabilidad; rectificaciones son filas nuevas. Ausencia de revisión no genera un actor ni decisión ficticios. Una descarga correcta, una fuente activa o una oferta cerrada no determinan la aprobación o rechazo editorial. No se heredan decisiones entre versiones/documentos y no existe «beca aprobada» general.

Oferente exige evidencia documental exacta y referencia justificada. Convenios no pueden aprobarse mientras falte representar suficientemente la participación formal ecuatoriana; tampoco basta la difusión por un portal ecuatoriano. No se crean/vinculan/publican convocatorias, no se resuelven incidencias y no se habilita publicación automática. Contrato, restricciones y diferencias en [suplemento de revisión](Modelo/Revision_administrativa_rastreo.md); instrucciones en [guía administrativa](consulta-administrativa-rastreo.md). Las secciones históricas siguientes describen etapas anteriores.

Meta de entrega: 3 de noviembre de 2026. Esta etapa programa únicamente comparación explicable de requisitos; las decisiones de rastreo y afinidad siguientes son reglas para etapas futuras, no funciones disponibles.

## Alcance y fuentes

- Público: ciudadanos ecuatorianos.
- Oferentes: entidades ecuatorianas y convenios con participación formal de una entidad ecuatoriana.
- Se excluyen ofertas extranjeras que un portal ecuatoriano solo difunde.
- Destinos de estudio nacionales o extranjeros.
- Rastreo diario por fuente y ejecución manual administrativa. En local depende de que el equipo y el proceso estén activos.
- Fuentes integradas progresivamente y verificadas; no afirmar cobertura de todas las becas de Ecuador.
- Publicación automática solo con fuente aprobada, oferente admisible, título, descripción, enlace oficial, requisitos identificables, beneficio descrito y al menos una opción con nivel, modalidad y destino.
- Cierre conocido y vigente, o carácter permanente explícito.
- Sin contradicciones importantes ni duplicados sin resolver.
- Información insuficiente o dudosa queda en revisión.
- El rastreo no sobrescribe silenciosamente correcciones manuales.

Estas condiciones de publicación automática no sustituyen silenciosamente la publicación manual existente. El modelo actual tiene una institución por convocatoria y no representa la evidencia de un convenio con participación formal ecuatoriana; se debe diseñar esa representación antes de integrar dichas fuentes. No se amplían los permisos ni la admisibilidad de oferentes mediante esta comparación.

## Comparación y presentación

- Información desconocida no equivale a incumplimiento.
- Documentos y certificados los verifica la entidad oferente.
- Una convocatoria se muestra una vez, con resultados separados por opción y una opción destacada.
- Opciones incompatibles se muestran en una sección separada; la convocatoria sigue consultable según su visibilidad pública.
- Comparar datos declarados no acredita títulos, idiomas ni documentos.

## Afinidad futura

- 70 % temática, 10 % nivel preferido, 10 % modalidad preferida y 10 % destino preferido.
- Afinidad separada del cumplimiento de requisitos.
- El porcentaje no representa probabilidad de adjudicación.
- Si faltan componentes para calcularlo, mostrar afinidad pendiente; no redistribuir pesos automáticamente.
- Los pesos son una decisión inicial que requiere validación con ejemplos revisados manualmente.

## Decisiones aprobadas el 26/10/2026 e implementación

Propuesta previa: propuesta-reglas-comparacion-v2.md. Modelo vigente: modelo/Modelo_logico_v06.json y suplemento Ampliacion_comparacion_v06.md. Se conserva el modelo v05 histórico.

- **Nivel académico:** niveles admitidos explícitos por requisito; no se infiere jerarquía ni que maestría sustituya grado. Un mínimo antiguo sin lista queda desconocido, incluso si el nivel declarado tiene el mismo nombre. El administrador debe transcribir la lista respaldada por las bases.
- **Título y área:** área de catálogo y título normalizado (Unicode NFC, espacios, mayúsculas), o equivalencia revisada con referencia a las bases, local al requisito. No se deducen equivalencias legales por IA, similitud o eliminación de acentos; diferencia sin equivalencia queda desconocida.
- **Misma formación:** grupos explícitos para condiciones académicas conjuntas. Una candidata que cumple todo basta; si ninguna cumple pero alguna no puede descartarse, pendiente; todas descartadas con datos conocidos, incumplimiento del grupo. La evidencia corresponde a la misma candidata, nunca a títulos diferentes. Independencia explícita permite condiciones separadas. Relación antigua pendiente no se convierte por suposición; no oculta incumplimientos ya comprobables.
- **Dedicación:** ambas en perfil satisface completa o parcial. Solo parcial no satisface completa. El valor ambas de requisitos antiguos conserva su significado de exigir esa disponibilidad, sin reescribirlo como cualquiera de las dos.
- **Residencia:** país por catálogo, nombres normalizados y equivalencias contextualizadas. Provincia necesita país; ciudad necesita país y provincia. Una lista territorial con varios contextos requiere mapeo explícito por contexto, incluso para nombres iguales. No se equiparan homónimos; diferencias de escritura conservan incertidumbre.
- **Destinos:** se evalúan comunes, opción y país. Alguna alternativa coincide: opción coincidente; ninguna coincide y alguna pendiente: opción pendiente; todas incumplen: opción incompatible. Modalidad virtual o destino extranjero no crean una exigencia de traslado. Solo se compara movilidad cuando una condición explícita la exige; no se usan preferencias como elegibilidad.
- **Documentos:** permanecen pendientes de la entidad oferente incluso con coincidencias declaradas. No se acreditan certificados ni se solicitan archivos.

## Evidencia todavía insuficiente

- **Promedio:** comparación de escalas idénticas implementada. Conversiones entre escalas distintas requieren fórmula concreta aprobada, extremos/rango, precisión, redondeo y referencia de esa convocatoria. No se proporcionó tal conversión: sigue desconocido. El campo de equivalencia literal no es ejecutable y nunca se usa eval.
- **Experiencia:** implementados filtro de área, recorte por fecha de referencia publicada y unión de intervalos superpuestos. Los intervalos son fechas, no meses calculados. Ausencia de registros sigue siendo no declarado. Falta una convención concreta aprobada para traducir esos periodos a meses (fracciones, extremos, discontinuidades); cualquier texto registrado es evidencia pendiente de formalización, no un algoritmo. No se asumen meses de 30 días ni equivalencias de jornadas.
- Registros antiguos sin lista admitida, vínculo académico, contexto territorial, ámbito de movilidad o evidencia suficiente siguen desconocidos. La nueva estructura permite completar evidencia administrativa sin editar JSON, con validación del servidor, revisión y auditoría.

## Persistencia y alcance

Cada consulta calcula los datos actuales, con no-store. TRA_RECOMENDACION exige configuración, similitud y afinidad; TRA_EVALUACION_REQUISITO depende de ella. No se crean ni se guardan ceros ficticios. La única migración nueva añade cuatro campos y restricciones de MAE_REQUISITO, sin convertir sus valores antiguos. No se implementan todavía IA, rastreo ni notificaciones; las reglas de fuentes y afinidad de arriba siguen siendo decisiones para etapas posteriores.

## Primera vista previa SIAU y nuevas decisiones aprobadas (26/10/2026)

El párrafo anterior describe el cierre de la comparación. Ahora se incorpora exclusivamente un comando manual de **descarga y observación local** de dos fichas SIAU, sin persistencia de negocio, publicación ni ejecución periódica. Véase [rastreo-fuentes-iniciales.md](rastreo-fuentes-iniciales.md). Las candidatas no quedan aprobadas automáticamente como fuentes publicables.

Decisiones aprobadas para la etapa posterior, **no implementadas por esta vista previa**:

- Los cambios observados en una fuente sobre una convocatoria publicada se proponen para revisión; se conserva la versión publicada hasta una decisión administrativa explícita.
- No sobrescribir correcciones manuales.
- Desaparición o fallo de acceso genera una incidencia; no cancela automáticamente una convocatoria.
- Las vencidas se conservan como cerradas, consultables por filtro y favoritos, fuera de las abiertas por defecto. El catálogo actual no se modifica en esta tarea; el ajuste de su selección predeterminada y sus regresiones quedan para el bloque correspondiente.

No se añadieron modelos, campos, migraciones, datos, IA, notificaciones ni rastreo programado. PUSAK se conserva únicamente como enlace de postulación; no se consulta ni se autentica automáticamente.

## Primer bloque de persistencia aprobado e implementado (27/10/2026)

La conclusión anterior corresponde a la vista previa. El usuario autorizó después las seis tablas de fuente, ejecución, documento, acceso, incidencia y revisión de configuración/incidencias; archivo privado separado, sin eliminación automática; ejecución manual al activar mediante administrador real; publicación automática deshabilitada.

Implementado en la app rastreo, con migraciones 0001/0002 y protección PostgreSQL del historial/auditoría. Almacenamiento efectivo D:\Datos_BecaNexo\rastreo. SIAU se registró desactivada y luego se activó mediante dos revisiones del administrador ID 1, elegido por coincidencia exacta de la cuenta indicada por el usuario, sin modificarla. La atribución CLI no es autenticación web.

La ejecución real 1 finalizó técnicamente con seis accesos/documentos y dos avisos de revisión documental pendiente. Ninguna aprobación documental o publicación se deriva de ese éxito. El módulo no cambia datos del catálogo ante 404, timeout, PDF cambiado o vigencia. No hay cron, IA ni notificaciones. El resto de la propuesta de persistencia sigue pendiente, no aprobado por extensión implícita de este bloque.

Véanse [suplemento efectivo](Modelo/Persistencia_rastreo_bloque1.md), [comandos](comandos-rastreo.md), [respaldo](respaldo-rastreo.md) y resultados reales en avance.md. Se conserva v0.6 histórico y se documenta por separado la ampliación.

## Segundo bloque aprobado e implementado (28/10/2026)

Identidad por fuente/URL, versiones inmutables, relaciones documentales exactas y observaciones por ejecución incorporadas con migraciones 0003/0004/0005. La ejecución real 2 confirmó dos publicaciones sin convocatoria, dos versiones y dos observaciones; no reconstruye la ejecución 1. Cambios/repetición se probaron con fixtures, no con descargas adicionales. No se hereda aprobación documental: ambos PDF siguen pendientes de revisión.

El [suplemento del bloque 2](Modelo/Persistencia_rastreo_bloque2.md) documenta manifiesto JSON, sello de transacción, pertenencia/inmutabilidad en PostgreSQL y contadores reales. Continúan pendientes revisión editorial, vinculación/creación de convocatorias, propuestas y publicación automática. Fuente activa sigue siendo distinta de fuente aprobada: SIAU conserva aprobación automática false. No se alteran decisiones académicas, precisión temporal, topes económicos ni reglas del catálogo.
