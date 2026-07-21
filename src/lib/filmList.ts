export type FilmListSort = 'title' | 'year' | 'tmdb' | 'personal'

interface SortableFilm {
  title: string
  year: number | null
  voteAverage: number | null
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

