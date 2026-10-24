# Alcance de BecaNexo

Proyecto de tesis de Ingeniería de Software que recomendará becas a ciudadanos ecuatorianos. Se admitirán únicamente ofertas de entidades ecuatorianas, aunque el destino de estudio podrá ser Ecuador u otro país.

## Usuarios y funciones previstas

Los roles serán postulante y administrador. El postulante podrá registrarse e iniciar sesión por correo, sin nombre de usuario; completar su perfil académico y preferencias; consultar catálogo y detalle de becas; guardar favoritos; recibir recomendaciones, explicaciones de coincidencias y notificaciones.

La administración gestionará convocatorias, opciones de estudio, beneficios y requisitos detallados, además de supervisar la información y el funcionamiento del sistema. Se rastrearán periódicamente fuentes seleccionadas.

Las recomendaciones combinarán similitud semántica ejecutada localmente y reglas explícitas de elegibilidad. Las explicaciones se basarán en la información declarada por el postulante y no constituirán una certificación de elegibilidad ni una adjudicación.

El postulante declarará idioma y nivel. No cargará certificados. Los certificados exigidos se describirán en los requisitos de cada beca; su verificación corresponderá a la entidad oferente durante la postulación externa.

## Límites

El sistema no tramitará postulaciones ni adjudicará becas. No utilizará APIs de pago. Las ofertas de entidades no ecuatorianas quedan fuera del alcance, independientemente del destino de estudio.

## Decisiones técnicas

- Backend en Django 5.2 y Django REST Framework, organizado como monolito modular.
- PostgreSQL local; futuro frontend en React, Vite y Tailwind CSS, preparando Node 24 LTS antes de implementarlo.
- Autenticación prevista mediante sesiones, con protección CSRF y comprobación de entradas y permisos en el servidor. Contraseñas protegidas mediante hashing de Django.
- Modelo de datos e interfaces ya diseñados, pendientes de incorporación antes de implementar los modelos de negocio.
- Tablas de negocio en mayúsculas y con prefijos por categoría, incluido `CAT_` para catálogos. Las diferencias entre el ER y las tablas auxiliares requeridas por Django se documentarán expresamente.

La primera etapa se limita a configuración y documentación. No incluye modelos, migraciones, endpoints ni frontend, ni cambios de datos o credenciales.
