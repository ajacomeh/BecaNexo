export function remaining(value, now) {
  const seconds = Math.max(0, Math.ceil((new Date(value).getTime() - now) / 1000))
  if (seconds >= 3600) return `${Math.floor(seconds / 3600)} h ${Math.floor((seconds % 3600) / 60)} min`
  if (seconds >= 60) return `${Math.floor(seconds / 60)} min ${seconds % 60} s`
  return `${seconds} s`
}
