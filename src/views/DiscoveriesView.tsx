import { useMemo, useState } from 'react'
import type { Recommendation } from '../domain/snapshot'
import { DiscoveryCard } from '../components/DiscoveryCard'
import { EmptyState } from '../components/EmptyState'
import { FilterBar } from '../components/FilterBar'
import { PageHeader } from '../components/PageHeader'
import { RatingLegend } from '../components/RatingLegend'
import { formatDate, searchFilm } from '../lib/format'

interface DiscoveriesViewProps {
  ai: Recommendation[]
  generatedAt: string | null
}

type DiscoverySort = 'score' | 'title' | 'year'

export function DiscoveriesView({ ai, generatedAt }: DiscoveriesViewProps) {
  const films = useMemo(() => [...ai], [ai])
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<DiscoverySort>('score')

  const visibleFilms = useMemo(
    () =>
      films
        .filter((film) => searchFilm(film, query, [film.rationale]))
        .sort((left, right) => {
          if (sort === 'title') return left.title.localeCompare(right.title)
          if (sort === 'year') return (right.year ?? 0) - (left.year ?? 0)
          return right.predictedRating - left.predictedRating || left.title.localeCompare(right.title)
        }),
    [films, query, sort],
  )

  return (
    <div className="view">
      <PageHeader count={films.length} eyebrow="Beyond the queue" title="Discoveries">
        AI recommendations verified against TMDB and filtered against the watched archive and watchlist.
      </PageHeader>
      {generatedAt ? (
        <p className="recommendation-date">Last recommendation run: {formatDate(generatedAt, 'full')}</p>
      ) : null}
      <RatingLegend label="Discovery rating legend" primaryLabel="Personal expected rating" />
      <FilterBar
        label="Search discoveries"
        onQueryChange={setQuery}
        query={query}
        resultCount={visibleFilms.length}
        selects={[
          {
            id: 'discovery-sort',
            label: 'Sort',
            options: [
              { label: 'Best match', value: 'score' },
              { label: 'Title A–Z', value: 'title' },
              { label: 'Newest release', value: 'year' },
            ],
            value: sort,
            onChange: (value) => setSort(value as DiscoverySort),
          },
        ]}
      />
      {visibleFilms.length > 0 ? (
        <div className="discovery-grid discovery-grid--archive">
          {visibleFilms.map((film) => (
            <DiscoveryCard discovery={film} key={`${film.source}-${film.mediaType}-${film.tmdbId}`} />
          ))}
        </div>
      ) : (
        <EmptyState title={films.length === 0 ? 'No discoveries published' : 'No films found'}>
          {films.length === 0
            ? 'Run the AI recommendation command to publish verified suggestions.'
            : 'Try another search.'}
        </EmptyState>
      )}
    </div>
  )
}
