const bools = [{ value: 'true', label: 'Sí' }, { value: 'false', label: 'No' }]
const choices = (rows) => rows.map((row) => ({ value: row.valor, label: row.nombre }))
const catalog = (rows) => rows.map((row) => ({ value: String(row.id), label: row.nombre }))

export function profileFields(c) {
  const area = { name: 'area', label: 'Área', options: catalog(c.areas), kind: 'id' }
  const nivel = { name: 'nivel', label: 'Nivel académico', options: choices(c.niveles), required: true }
  return {
    personal: [
      { name: 'fecha_nacimiento', label: 'Fecha de nacimiento', type: 'date', hint: 'Opcional. Se usará cuando existan requisitos de edad.' },
      { name: 'residencia', label: 'País de residencia', options: catalog(c.paises), kind: 'id' },
      { name: 'provincia_residencia', label: 'Provincia de residencia' },
      { name: 'ciudad_residencia', label: 'Ciudad de residencia' },
    ],
    availability: [
      { name: 'dedicacion_disponible', label: 'Dedicación disponible', options: choices(c.dedicaciones) },
      { name: 'disponible_traslado', label: '¿Puedes trasladarte?', options: bools, kind: 'boolean' },
      { name: 'disponible_extranjero', label: '¿Puedes estudiar en el extranjero?', options: bools, kind: 'boolean' },
    ],
    formaciones: [nivel,
      { name: 'estado_estudios', label: 'Estado de estudios', options: choices(c.estados), required: true },
      { name: 'carrera', label: 'Carrera / programa', maxLength: 200, required: true },
      { name: 'titulo_obtenido', label: '¿Título obtenido?', options: bools, required: true, kind: 'boolean' },
      { name: 'nombre_titulo', label: 'Nombre del título' }, { ...area, label: 'Área de formación' },
      { name: 'institucion', label: 'Institución de formación', maxLength: 200 },
      { name: 'fecha_finalizacion', label: 'Fecha de finalización', type: 'date' },
      { name: 'promedio', label: 'Promedio obtenido', type: 'number' },
      { name: 'escala_min', label: 'Mínimo de la escala', type: 'number' },
      { name: 'escala_max', label: 'Máximo de la escala', type: 'number' },
    ],
    experiencias: [{ name: 'cargo', label: 'Cargo / actividad' }, area,
      { name: 'fecha_inicio', label: 'Fecha de inicio', type: 'date', required: true },
      { name: 'fecha_fin', label: 'Fecha final', type: 'date' },
      { name: 'actual', label: '¿Continúa actualmente?', options: bools, required: true, kind: 'boolean' },
      { name: 'descripcion', label: 'Descripción de la experiencia', type: 'textarea', wide: true }],
    idiomas: [{ name: 'idioma', label: 'Idioma', options: catalog(c.idiomas), kind: 'id', required: true },
      { name: 'nivel', label: 'Nivel declarado (MCER)', options: choices(c.niveles_idioma) }],
    preferencias: [{ ...nivel, label: 'Nivel deseado' }, { name: 'modalidad', label: 'Modalidad deseada', options: choices(c.modalidades), required: true }],
    areas: [{ ...area, label: 'Área de interés', required: true }],
    destinos: [{ name: 'pais', label: 'País de destino', options: catalog(c.paises), kind: 'id', required: true }],
  }
}
