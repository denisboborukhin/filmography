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

export function formatScore(value: number | null): string {
  return value === null ? '—' : value.toFixed(1)
}

export function posterUrl(path: string | null): string | null {
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  return `https://image.tmdb.org/t/p/w500${path.startsWith('/') ? path : `/${path}`}`
}

export function catalogUrl(film: Pick<Film, 'mediaType' | 'tmdbId'>): string | null {
  if (film.tmdbId === null) return null
  return `https://www.themoviedb.org/${film.mediaType}/${film.tmdbId}`
}

export function searchFilm(film: Film, query: string, extra: string[] = []): boolean {
  const normalized = query.trim().toLocaleLowerCase()
  if (!normalized) return true
  return [film.title, String(film.year ?? ''), film.overview, ...film.genres, ...extra]
    .join(' ')
    .toLocaleLowerCase()
    .includes(normalized)
}
