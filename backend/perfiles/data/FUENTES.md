# Catálogos iniciales de perfil

Preparados el 25 de octubre de 2026. Se cargan desde archivos/código versionados, sin acceso a red durante la carga o el uso de la aplicación.

## Países y territorios

`paises.json` contiene 249 códigos ISO 3166-1 alfa-2. Los códigos proceden del [catálogo de pycountry](https://github.com/pycountry/pycountry/blob/main/src/pycountry/databases/iso3166-1.json), que distribuye datos de Debian iso-codes. Los nombres españoles se tomaron de [Unicode CLDR, locale es](https://github.com/unicode-org/cldr-json/blob/main/cldr-json/cldr-localenames-full/main/es/territories.json). Se seleccionaron solo los códigos presentes en ISO; no se añadieron agrupaciones regionales, instituciones o becas.

Fuentes de descarga:

- https://raw.githubusercontent.com/pycountry/pycountry/main/src/pycountry/databases/iso3166-1.json
- https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json/cldr-localenames-full/main/es/territories.json

SHA-256 del archivo local: `8e586e1e18a9917e94e478d096cdda51298e388327e667d315d709e988cf8f95`.

La instantánea local fija la cobertura de esta entrega aunque cambien las ramas de origen. Incluye países y territorios con código ISO; no constituye una declaración política ni un catálogo de becas disponibles. `EC` identifica Ecuador tanto al cargar como al crear perfiles. Los nombres localizados pueden diferir de denominaciones oficiales extensas. Atribución: datos de Unicode, Inc. y colaboradores de CLDR ([licencia Unicode](https://www.unicode.org/license.txt)); códigos de iso-codes/pycountry ([procedencia y licencia](https://github.com/pycountry/pycountry)).

## Idiomas

Selección inicial de 12 idiomas: es, en, fr, de, pt, it, zh, ja, ko, ar, qu y jiv. Los códigos se verificaron contra [ISO 639 en pycountry](https://github.com/pycountry/pycountry/blob/main/src/pycountry/databases/iso639-3.json). Se usa alfa-2 cuando existe; `jiv` es alfa-3 para Shuar. `qu` representa Quechua como macrolengua, sin inferir una variedad concreta. Las denominaciones españolas están declaradas en el comando.

Es una selección inicial, no todos los idiomas del mundo. Puede ampliarse mediante una carga revisada; no existe escritura pública de catálogo. Los niveles A1, A2, B1, B2, C1 y C2 corresponden al [MCER del Consejo de Europa](https://www.coe.int/en/web/common-european-framework-reference-languages/introduction-and-context); NULL significa desconocido. No se transforma lengua materna, un certificado o un nivel de otro marco en MCER automáticamente.

## Áreas

Se incorporan las 11 áreas amplias 00–10 de [ISCED-F 2013 / CINE-F de UNESCO UIS](https://uis.unesco.org/en/methods-and-tools/isced), con denominaciones españolas en el comando. Esta entrega utiliza áreas amplias, no una clasificación exhaustiva de carreras o especialidades. Por ejemplo, informática está comprendida en «Tecnologías de la información y la comunicación». El ER solo prevé `id` y `nombre` en CAT_AREA: no se añadió una columna de código ni una jerarquía.

## Reproducción

Desde la raíz, con las migraciones aplicadas:

```powershell
.\.venv\Scripts\python.exe backend\manage.py cargar_catalogos
```

El comando ejecuta una transacción: update_or_create por código para países/idiomas, get_or_create por nombre para áreas. Repetirlo conserva IDs, no duplica entradas y no elimina catálogos adicionales. Actualiza los nombres de los códigos incluidos a los valores de la instantánea. Para renombrar un área ya utilizada debe diseñarse un cambio explícito: cambiar su nombre en la lista por sí solo crearía otra área.
