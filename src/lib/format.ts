import type { Film } from '../domain/snapshot'

const shortDateFormatter = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

const fullDateFormatter = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
})

export function formatDate(value: string | null, style: 'short' | 'full' = 'short'): string {
  if (!value) return 'Date not recorded'
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value)
  if (Number.isNaN(date.getTime())) return value
  return (style === 'full' ? fullDateFormatter : shortDateFormatter).format(date)
}

export function formatScore(value: number | null, fixedDecimal = false): string {
  if (value === null) return '—'
  if (fixedDecimal) return value.toFixed(1)
  return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1)
}

export function posterUrl(path: string | null): string | null {
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  return `https://image.tmdb.org/t/p/w500${path.startsWith('/') ? path : `/${path}`}`
}

export function filmLabel(film: Pick<Film, 'title' | 'year'>): string {
  return film.year ? `${film.title} (${film.year})` : film.title
}

export function searchFilm(film: Film, query: string, extra: string[] = []): boolean {
  const normalized = query.trim().toLocaleLowerCase()
  if (!normalized) return true
  return [film.title, String(film.year ?? ''), film.overview, ...film.genres, ...extra]
    .join(' ')
    .toLocaleLowerCase()
    .includes(normalized)
}
