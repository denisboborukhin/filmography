import { useMemo, useState } from 'react'
import type { Film } from '../domain/snapshot'
import { compareFilmListItems, genresForFilms, type FilmListSort } from '../lib/filmList'
import { searchFilm } from '../lib/format'

export function useFilmList<TFilm extends Film>(
  films: TFilm[],
  searchText: (film: TFilm) => string[],
  personalScore: (film: TFilm) => number | null,
  priority?: (film: TFilm) => number,
) {
  const [query, setQuery] = useState('')
  const [genre, setGenre] = useState('all')
  const [sort, setSort] = useState<FilmListSort>('title')
  const genres = useMemo(() => genresForFilms(films), [films])
  const visibleFilms = useMemo(
    () =>
      films
        .filter(
          (film) =>
            searchFilm(film, query, searchText(film)) &&
            (genre === 'all' || film.genres.includes(genre)),
        )
        .sort(
          (left, right) =>
            (priority?.(left) ?? 0) - (priority?.(right) ?? 0) ||
            compareFilmListItems(left, right, sort, personalScore),
        ),
    [films, genre, personalScore, priority, query, searchText, sort],
  )

  return {
    genre,
    genres,
    query,
    setGenre,
    setQuery,
    setSort,
    sort,
    visibleFilms,
  }
}
