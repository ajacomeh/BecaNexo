# Reglas de trabajo de BecaNexo

BecaNexo es un proyecto de tesis de Ingeniería de Software para recomendar becas a ciudadanos ecuatorianos. Solo admite ofertas de entidades ecuatorianas; el destino de estudio puede ser Ecuador u otro país. Los roles son postulante y administrador.

## Alcance y arquitectura

- Desarrollar por etapas, con responsabilidades claras, como monolito modular.
- Backend: Django 5.2 y Django REST Framework; PostgreSQL local. Frontend futuro: React con Vite y Tailwind CSS; preparar Node 24 LTS antes del frontend (Node 25 informado actualmente).
- Prever registro e inicio de sesión por correo, sin nombre de usuario, mediante sesiones y protección CSRF.
- El alcance funcional incluye perfil académico y preferencias; catálogo, detalle y favoritos; administración de convocatorias, opciones de estudio, beneficios y requisitos detallados; rastreo periódico de fuentes seleccionadas; recomendación por similitud semántica local y reglas explícitas de elegibilidad; explicaciones según información declarada; notificaciones y supervisión administrativa.
- El postulante declara idioma y nivel, sin cargar certificados. Los certificados exigidos se describen en los requisitos de la beca y los verifica la entidad oferente durante la postulación externa.
- El sistema no realiza postulaciones ni adjudica becas. No utilizar APIs de pago.

## Datos y seguridad

- Consultar el modelo de datos actualizado y las interfaces antes de crear entidades. Los diseños ya existen, pero deben incorporarse al repositorio antes de implementar modelos de negocio. No inferir entidades para suplir su ausencia.
- Usar nombres de tablas de negocio en mayúsculas y prefijos por categoría, incluido `CAT_` para catálogos.
- Documentar cualquier diferencia entre el ER y las tablas auxiliares que necesita Django, incluidas autenticación, sesiones, permisos y administración.
- Validar entradas y comprobar permisos en el servidor. Usar los mecanismos de hashing de Django para contraseñas.
- No desactivar CSRF para resolver errores de integración.
- Acompañar autenticación y autorización con pruebas.
- Leer la configuración privada desde el entorno; mantener `DEBUG` desactivado por defecto y no introducir claves secretas de respaldo en el código.
- No imprimir, copiar, versionar ni registrar secretos de `.env` u otras configuraciones. No registrar datos personales innecesarios.
- Mantener `.env.example` sin secretos y las futuras migraciones dentro del control de versiones.

## Entorno, verificación y documentación

- Trabajar en Windows 11 con PowerShell, desde la raíz del repositorio. Usar `.\.venv\Scripts\python.exe`; el backend está en `backend/` y su configuración en `backend/config/`.
- La configuración local privada está en `backend/.env`. PostgreSQL local usa la base `becanexo_db` y el usuario `becanexo_app`; no cambiar datos ni credenciales sin una tarea que lo autorice.
- Ejecutar `.\.venv\Scripts\python.exe backend/manage.py check` para comprobar la configuración.
- Mantener documentación de cambios y decisiones en `docs/`. Registrar únicamente comprobaciones realmente ejecutadas: no inventar resultados de pruebas.
- En la primera etapa solo revisar configuración y documentación: no crear modelos, migraciones, endpoints ni frontend; no ejecutar `migrate`, instalar herramientas globales, hacer commits ni publicar el repositorio.
- Antes de la primera migración, resolver el diseño de autenticación por correo con el modelo actualizado y documentar las tablas auxiliares de Django.
