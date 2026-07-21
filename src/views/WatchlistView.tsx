import { useMemo, useState } from 'react'
import type { WatchlistFilm } from '../domain/snapshot'
import { EmptyState } from '../components/EmptyState'
import { FilmListControls } from '../components/FilmListControls'
import { PageHeader } from '../components/PageHeader'
import { RatingLegend } from '../components/RatingLegend'
import { WatchlistCard } from '../components/WatchlistCard'
import { compareFilmListItems, type FilmListSort } from '../lib/filmList'
import { searchFilm } from '../lib/format'

interface WatchlistViewProps {
  films: WatchlistFilm[]
}

export function WatchlistView({ films }: WatchlistViewProps) {
  const activeFilms = useMemo(() => films.filter((film) => !film.dismissed), [films])
  const [query, setQuery] = useState('')
  const [genre, setGenre] = useState('all')
  const [sort, setSort] = useState<FilmListSort>('title')
  const genres = useMemo(
    () => [...new Set(activeFilms.flatMap((film) => film.genres))].sort(),
    [activeFilms],
  )

  const visibleFilms = useMemo(
    () =>
      activeFilms
        .filter(
          (film) =>
            searchFilm(film, query, [...film.tags, film.notes]) &&
            (genre === 'all' || film.genres.includes(genre)),
        )
        .sort((left, right) => compareFilmListItems(left, right, sort, (film) => film.interest)),
    [activeFilms, genre, query, sort],
  )

  return (
    <div className="view">
      <PageHeader count={activeFilms.length} eyebrow="For another evening" title="Watchlist">
        A considered queue, ordered by how strongly each film is calling right now.
      </PageHeader>
      <RatingLegend label="Watchlist score legend" primaryLabel="Personal expected score" />
      <FilmListControls
        genre={genre}
        genreId="watchlist-genre"
        genres={genres}
        onGenreChange={setGenre}
        onQueryChange={setQuery}
        onSortChange={setSort}
        personalSortLabel="Highest expected personal score"
        query={query}
        resultCount={visibleFilms.length}
        searchLabel="Search the watchlist"
        sort={sort}
        sortId="watchlist-sort"
      />
      {visibleFilms.length > 0 ? (
        <div className="watchlist-grid">
          {visibleFilms.map((film) => (
            <WatchlistCard
              film={film}
              key={`${film.mediaType}-${film.tmdbId ?? film.title}-${film.year}`}
            />
          ))}
        </div>
      ) : (
        <EmptyState title={activeFilms.length === 0 ? 'The watchlist is clear' : 'No films found'}>
          {activeFilms.length === 0
            ? 'Add titles to the Markdown watchlist and rebuild the journal.'
            : 'Try a different title or genre.'}
        </EmptyState>
      )}
    </div>
  )
}
