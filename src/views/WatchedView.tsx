import { useMemo, useState } from 'react'
import type { WatchedFilm } from '../domain/snapshot'
import { EmptyState } from '../components/EmptyState'
import { FilterBar } from '../components/FilterBar'
import { PageHeader } from '../components/PageHeader'
import { ReviewCard } from '../components/ReviewCard'
import { searchFilm } from '../lib/format'

interface WatchedViewProps {
  films: WatchedFilm[]
}

type WatchedSort = 'date' | 'rating' | 'title'

export function WatchedView({ films }: WatchedViewProps) {
  const [query, setQuery] = useState('')
  const [genre, setGenre] = useState('all')
  const [minimumRating, setMinimumRating] = useState('0')
  const [sort, setSort] = useState<WatchedSort>('date')
  const genres = useMemo(
    () => [...new Set(films.flatMap((film) => film.genres))].sort(),
    [films],
  )

  const visibleFilms = useMemo(() => {
    const selectedMinimum = Number(minimumRating)
    return films
      .filter(
        (film) =>
          searchFilm(film, query, [...film.tags, film.review]) &&
          (genre === 'all' || film.genres.includes(genre)) &&
          film.rating >= selectedMinimum,
      )
      .sort((left, right) => {
        if (sort === 'rating') return right.rating - left.rating || left.title.localeCompare(right.title)
        if (sort === 'title') return left.title.localeCompare(right.title)
        return (right.watchedAt ?? '').localeCompare(left.watchedAt ?? '')
      })
  }, [films, genre, minimumRating, query, sort])

  return (
    <div className="view">
      <PageHeader count={films.length} eyebrow="The archive" title="Watched">
        Every score and note, from fleeting impressions to the films that refused to leave.
      </PageHeader>
      <FilterBar
        label="Search reviews, titles, or tags"
        onQueryChange={setQuery}
        query={query}
        resultCount={visibleFilms.length}
        selects={[
          {
            id: 'watched-genre',
            label: 'Genre',
            options: [
              { label: 'All genres', value: 'all' },
              ...genres.map((item) => ({ label: item, value: item })),
            ],
            value: genre,
            onChange: setGenre,
          },
          {
            id: 'minimum-rating',
            label: 'Rating',
            options: [0, 6, 7, 8, 9].map((rating) => ({
              label: rating === 0 ? 'Any rating' : `${rating}+`,
              value: String(rating),
            })),
            value: minimumRating,
            onChange: setMinimumRating,
          },
          {
            id: 'watched-sort',
            label: 'Sort',
            options: [
              { label: 'Recently watched', value: 'date' },
              { label: 'Highest rated', value: 'rating' },
              { label: 'Title A–Z', value: 'title' },
            ],
            value: sort,
            onChange: (value) => setSort(value as WatchedSort),
          },
        ]}
      />
      {visibleFilms.length > 0 ? (
        <div className="review-list">
          {visibleFilms.map((film) => (
            <ReviewCard film={film} key={`${film.mediaType}-${film.tmdbId ?? film.title}-${film.year}`} />
          ))}
        </div>
      ) : (
        <EmptyState title={films.length === 0 ? 'No reviews yet' : 'No matching reviews'}>
          {films.length === 0
            ? 'Import your review notes and rebuild the journal to fill this archive.'
            : 'Try a broader search or clear one of the filters.'}
        </EmptyState>
      )}
    </div>
  )
}
