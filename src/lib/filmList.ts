export type FilmListSort = 'title' | 'year' | 'tmdb' | 'personal'

interface FilmIdentity {
  mediaType: 'movie' | 'tv'
  tmdbId: number | null
  title: string
  year: number | null
}

interface SortableFilm extends Pick<FilmIdentity, 'title' | 'year'> {
  voteAverage: number | null
}

export function filmKey(film: FilmIdentity): string {
  return `${film.mediaType}-${film.tmdbId ?? film.title}-${film.year ?? 'unknown'}`
}

export function genresForFilms(films: { genres: string[] }[]): string[] {
  return [...new Set(films.flatMap((film) => film.genres))].sort()
}

export function compareFilmListItems<TFilm extends SortableFilm>(
  left: TFilm,
  right: TFilm,
  sort: FilmListSort,
  personalScore: (film: TFilm) => number | null,
): number {
  if (sort === 'year') {
    return (right.year ?? 0) - (left.year ?? 0) || compareTitle(left, right)
  }
  if (sort === 'tmdb') {
    return nullableScore(right.voteAverage) - nullableScore(left.voteAverage) || compareTitle(left, right)
  }
  if (sort === 'personal') {
    return nullableScore(personalScore(right)) - nullableScore(personalScore(left)) || compareTitle(left, right)
  }
  return compareTitle(left, right)
}

function compareTitle(left: SortableFilm, right: SortableFilm): number {
  return left.title.localeCompare(right.title)
}

function nullableScore(value: number | null): number {
  return value ?? -1
}
