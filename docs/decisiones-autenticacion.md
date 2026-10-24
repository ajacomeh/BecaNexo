# Decisiones de autenticación — etapa 2

Fecha: 24 de octubre de 2026.

Fuentes revisadas: `Modelo/Modelo_logico_v05.json` (MAE_USUARIO), `Modelo/Diccionario.md` y `Modelo/Reglas_y_requisitos.md`. La carpeta existente se llama `Modelo`, con mayúscula inicial. Los tres documentos coinciden en los campos de usuario; no se encontraron contradicciones en esta entidad.

## Mapeo lógico y físico

| Campo del ER / columna PostgreSQL | Campo Django | Decisión |
|---|---|---|
| id | id | BigAutoField, clave primaria bigint generada |
| email | email | EmailField de 254 caracteres, obligatorio y único sin distinguir mayúsculas |
| password_hash | password | CharField de 128 caracteres; hashing y comprobación de Django |
| nombre | nombre | CharField de 180 caracteres, obligatorio; nombre visible, no credencial |
| rol | rol | CharField de 20 caracteres: postulante o administrador; valor inicial postulante |
| activo | is_active | BooleanField, verdadero por defecto |
| creado_en | creado_en | DateTimeField con timezone.now, no editable en formularios |

La tabla física se llama `MAE_USUARIO`. No hay campos `username` ni `nombre_usuario`. `AUTH_USER_MODEL = "usuarios.Usuario"` se configura antes de la primera migración. El modelo hereda de AbstractBaseUser y PermissionsMixin. `USERNAME_FIELD` es `email`; `REQUIRED_FIELDS` contiene `nombre`.

## Correo, contraseñas e integridad

La política de correo consiste en quitar espacios exteriores con `strip()` y convertir todo el correo a minúsculas con `lower()`. Se comparte entre el manager, la limpieza y guardado del modelo y los formularios de administración. No se eliminan puntos ni sufijos `+`, ni se aplican reglas particulares de proveedores.

Se configura explícitamente `django.contrib.auth.backends.ModelBackend`. Sus búsquedas usan `get_by_natural_key` y `aget_by_natural_key` del manager: normalizan la entrada y consultan por `email__iexact`. Así se conserva la verificación de contraseña, el rechazo de usuarios inactivos y el comportamiento de seguridad de Django, sin duplicar el backend. El formulario de login incorporado de Django Admin llama técnicamente `username` a su entrada, pero la etiqueta y la identidad corresponden al correo; esto no crea una credencial adicional ni una columna username.

La migración declara `UniqueConstraint(Lower(Trim("email")))`, que PostgreSQL implementará mediante un índice único de expresión, además de `unique=True` en el campo para la integración estándar con Django. El índice impide duplicados por mayúsculas o espacios ordinarios exteriores incluso si se omite el manager. `QuerySet.update`, `bulk_create` y SQL directo no ejecutan la normalización Python: no deben usarse para altas o cambios de correo. `Trim` SQL no equivale a `strip()` para todo carácter Unicode de espacio; la entrada de aplicación siempre debe pasar por la política compartida.

Se añaden CHECK para el dominio de rol y para que nombre y correo contengan algún carácter no blanco; los campos son NOT NULL. La validación de formato de correo ocurre en Django. El manager valida campos y contraseña antes de guardar; los conflictos de unicidad se resuelven en la base de datos y pueden producir IntegrityError. Los futuros endpoints deberán convertirlos en respuestas controladas sin exponer detalles internos.

Se usan `set_password`, `check_password` y los validadores configurados de Django, nunca algoritmos propios. `create_user` permite `password=None`, que genera una contraseña inutilizable según la convención de Django; no permite iniciar sesión por contraseña. `create_superuser` exige contraseña y los valores rol=administrador, is_active=True, is_staff=True e is_superuser=True; rechaza valores contradictorios. `create_user` crea por defecto un postulante activo sin privilegios; sus argumentos explícitos son una API interna de confianza, no datos que un futuro endpoint de registro deba aceptar del cliente.

## Campos y tablas técnicas adicionales al ER

| Elemento | Finalidad |
|---|---|
| MAE_USUARIO.last_login | Fecha del último inicio de sesión; nullable, gestionada por Django |
| MAE_USUARIO.is_staff | Permite acceso a Django Admin si la cuenta también está activa; no equivale al rol administrador |
| MAE_USUARIO.is_superuser | Concede todos los permisos de Django a un usuario activo |
| MAE_USUARIO_groups | Asociación técnica de usuarios con grupos, heredada de PermissionsMixin |
| MAE_USUARIO_user_permissions | Permisos individuales de usuario, heredados de PermissionsMixin |
| auth_group | Grupos de permisos de Django |
| auth_permission | Permisos asociados a modelos y tipos de contenido |
| auth_group_permissions | Asociación entre grupos y permisos |
| django_content_type | Tipos de contenido referenciados por permisos y administración |
| django_admin_log | Historial técnico de acciones del administrador de Django |
| django_session | Persistencia de sesiones del backend configurado |
| django_migrations | Registro de migraciones aplicadas |

Las relaciones técnicas usan las convenciones automáticas de Django y no agregan entidades de negocio al ER. No se renombraron las tablas internas del framework. `auth_user` no será la tabla de usuario, dado el modelo intercambiado. Esta lista describe el esquema previsto: ninguna de estas tablas se creó durante esta etapa.

El rol de negocio no concede permisos automáticamente. Un administrador de negocio puede tener `is_staff=False`. Los permisos de futuros endpoints deben comprobarse expresamente en el servidor.

## Administración y límites

UsuarioAdmin utiliza formularios derivados de BaseUserCreationForm y UserChangeForm. El alta exige confirmación y validación de contraseña; la edición muestra el hash como solo lectura y conserva el mecanismo de cambio de contraseña de Django. No incluye username. Solo los superusuarios pueden agregar, modificar o eliminar cuentas desde esta administración, evitando que un staff cambie contraseñas o eleve privilegios por permisos delegados sobre usuarios. La lectura continúa sujeta a los permisos estándar de Django.

Se mantiene el middleware CSRF. No hay endpoints de registro, inicio o cierre de sesión de la aplicación; se implementarán y probarán en la siguiente etapa. No se implementaron perfiles ni otras entidades del ER.

## Verificación y siguientes pasos

La migración `usuarios/0001_initial.py` se generó sin aplicarla. Incluye la dependencia de auth necesaria para los permisos y grupos.

Pasaron `manage.py check`, `manage.py makemigrations --check --dry-run` y las siete pruebas de `usuarios.tests.UsuarioSinBaseTests`. El ejecutor confirmó que omitió la preparación de la base de datos.

Las nueve pruebas de `usuarios.tests.UsuarioBaseTests` cubren persistencia del hash, normalización, duplicados mediante manager y escritura directa, autenticación con variantes de correo, contraseña incorrecta, usuario inexistente e inactivo, superusuarios, restricciones de rol/campos y formularios de alta y edición. Inicialmente quedaron pendientes de una base PostgreSQL independiente.

En la verificación posterior del 24 de octubre se configuró TEST.NAME como `test_becanexo_db`, creada manualmente por el responsable, y se comprobó que difiere de `becanexo_db`, sin TEST.MIRROR. El comando `.\.venv\Scripts\python.exe backend\manage.py test usuarios --keepdb --verbosity 2` aprobó las 16 pruebas, sin errores ni omisiones, aplicando migraciones únicamente en la base de pruebas y conservándola al terminar. No se cambiaron credenciales, permisos de PostgreSQL, ni se ejecutaron migrate sobre desarrollo o createsuperuser. El detalle está en `avance.md`.
