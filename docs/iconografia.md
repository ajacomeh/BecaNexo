# Iconografía del frontend

Incorporada el 28/10/2026, pendiente de revisión y sin commit. La bandeja de rastreo previamente validada quedó guardada por separado en `56bc387` (`feat: agregar consulta administrativa de rastreo`), con 16 archivos y sin outputs, secretos ni documentos descargados.

## Biblioteca y criterios

No existía una biblioteca de iconos: el SVG de bienvenida es una ilustración y se conserva. Se añadió únicamente **lucide-react 1.63.0**, licencia ISC, compatible con React 19 según sus peerDependencies consultadas en npm. package.json y package-lock.json actualizados; instalación informó un paquete añadido y cero vulnerabilidades. La [documentación oficial de Lucide para React](https://lucide.dev/guide/react) confirma componentes SVG locales e importaciones específicas con eliminación de código no utilizado.

- `components/Icon.jsx` importa explícitamente los iconos utilizados y centraliza sus nombres semánticos, trazo 1.8 y atributos decorativos. Sin importación de todo el catálogo, CDN, fuentes de iconos ni peticiones remotas en ejecución.
- Una sola familia de contorno, color heredado; 18 px en acciones y aproximadamente 21 px en navegación. Sin emojis. Se conserva la ilustración de bienvenida y se sustituyen sus flechas decorativas por la misma familia.
- Texto visible conservado; SVG con aria-hidden y focusable=false. Ningún estado depende solo del color o del icono. No se agregaron botones sin texto.
- Button admite un icono explícito y lo sustituye por carga únicamente cuando busy es verdadero. Disabled sin operación mantiene cursor not-allowed; carga usa wait. La animación respeta prefers-reduced-motion.
- CSS compartido alinea iconos y texto sin comprimir el SVG; las etiquetas pueden ocupar varias líneas. No se cambiaron colores, tipografía, rutas, permisos, peticiones ni decisiones de negocio.

## Cobertura

Navegación lateral e Inicio para postulante/administrador; bienvenida y accesos de cuenta; perfil y preferencias; catálogo, detalle y favoritos; comparación; gestión de convocatorias, editor y oferentes; consulta de rastreo. Acciones de búsqueda/limpieza, alta/edición/guardado/cancelación/eliminación, detalle/retorno, descarga, sitio oficial y paginación. Mensajes de error/información/éxito y resultados de comparación conservan sus textos.

Se reutilizan Button, Message y los formularios compartidos. OfferForm permite indicar el icono de búsqueda en los filtros, sin inferirlo del texto ni cambiar su lógica de envío. No se añadieron iconos a cada atributo de las fichas.

## Verificaciones realizadas

- `npm.cmd test`: **105 pruebas aprobadas**, 11 archivos, cero fallidas u omitidas, 15,53 s. No se modificaron los selectores ni las expectativas de las pruebas existentes.
- `npm.cmd run lint`: correcto, incluido el nuevo recorrido de navegador.
- `npm.cmd run build`: correcto. Bundle JS 373,27 kB / 112,52 kB gzip; solo un paquete añadido. El número de módulos procesados por Vite no equivale a iconos incluidos en el bundle final.
- `npm.cmd run test:e2e -- --config playwright.icons.config.js`: **5 pruebas aprobadas**, secuenciales, 23,8 s. Incluye los tres recorridos de rastreo existentes y dos nuevos para ambos roles. Escritorio 1440×900 y móvil 390/320×900; capturas revisadas, sin desbordamientos observados. Nombres accesibles, navegación, foco, cancelación, errores y carga comprobados. Un botón ocupado muestra spinner y wait; Cancelar deshabilitado y los extremos de paginación no muestran carga.
- Los recorridos autenticados usan API simulada, incluidos PATCH de prueba y datos sintéticos de catálogo/comparación. No crean sesiones ni registros en desarrollo. Se corrigió el mock inicial que respondía al PATCH como si fuera GET antes de comprobar los estados de guardado; no se cambió la implementación para ocultar el fallo.
- Backend HTTP real: rechazo 403 de consulta y descarga anónimas de rastreo. No se probó una sesión administrativa real ni se modificaron cuentas. No se cambiaron archivos de backend/modelos/migraciones durante la iconización.
- Las capturas de Playwright quedan en frontend/test-results, excluido de Git. Los cambios de iconografía quedan sin stage/commit. Pendiente: revisión visual del usuario con su sesión habitual; no hay comprobaciones automáticas fallidas pendientes.

## Repetir la comprobación

Desde la raíz, usar Node 24:

```powershell
$env:PATH = 'D:\Herramientas\node-v24.22.1-win-x64;' + $env:PATH
Set-Location frontend
npm.cmd test
npm.cmd run lint
npm.cmd run build
npm.cmd run test:e2e -- --config playwright.icons.config.js
```

Abrir `/becas`, revisar navegación y filtros, entrar al detalle y comparar requisitos como postulante. Como administrador, revisar `/gestion/convocatorias`, `/gestion/instituciones` y `/gestion/rastreo`. Comprobar Editar nombre → Cancelar sin guardar, foco con Tab y navegación en móvil. El recorrido automatizado simula el error/guardado para no modificar cuentas reales.
