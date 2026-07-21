import { useMemo, useState } from 'react'
import type { WatchlistFilm } from '../domain/snapshot'
import { EmptyState } from '../components/EmptyState'
import { FilterBar } from '../components/FilterBar'
import { PageHeader } from '../components/PageHeader'
import { RatingLegend } from '../components/RatingLegend'
import { WatchlistCard } from '../components/WatchlistCard'
import { searchFilm } from '../lib/format'

interface WatchlistViewProps {
  films: WatchlistFilm[]
}

type WatchlistSort = 'interest' | 'title' | 'year'

export function WatchlistView({ films }: WatchlistViewProps) {
  const activeFilms = useMemo(() => films.filter((film) => !film.dismissed), [films])
  const [query, setQuery] = useState('')
  const [genre, setGenre] = useState('all')
  const [sort, setSort] = useState<WatchlistSort>('interest')
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
        .sort((left, right) => {
          if (sort === 'title') return left.title.localeCompare(right.title)
          if (sort === 'year') return (right.year ?? 0) - (left.year ?? 0)
          return (right.interest ?? -1) - (left.interest ?? -1) || left.title.localeCompare(right.title)
        }),
    [activeFilms, genre, query, sort],
  )

  return (
    <div className="view">
      <PageHeader count={activeFilms.length} eyebrow="For another evening" title="Watchlist">
        A considered queue, ordered by how strongly each film is calling right now.
      </PageHeader>
      <RatingLegend label="Watchlist rating legend" primaryLabel="Personal expected rating" />
      <FilterBar
        label="Search the watchlist"
        onQueryChange={setQuery}
        query={query}
        resultCount={visibleFilms.length}
        selects={[
          {
            id: 'watchlist-genre',
            label: 'Genre',
            options: [
              { label: 'All genres', value: 'all' },
              ...genres.map((item) => ({ label: item, value: item })),
            ],
            value: genre,
            onChange: setGenre,
          },
          {
            id: 'watchlist-sort',
            label: 'Sort',
            options: [
              { label: 'Highest interest', value: 'interest' },
              { label: 'Title A–Z', value: 'title' },
              { label: 'Newest release', value: 'year' },
            ],
            value: sort,
            onChange: (value) => setSort(value as WatchlistSort),
          },
        ]}
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
