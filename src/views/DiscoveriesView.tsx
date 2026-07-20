import { useMemo, useState } from 'react'
import type { Recommendation } from '../domain/snapshot'
import { DiscoveryCard } from '../components/DiscoveryCard'
import { EmptyState } from '../components/EmptyState'
import { FilterBar } from '../components/FilterBar'
import { PageHeader } from '../components/PageHeader'
import { formatDate, searchFilm } from '../lib/format'

interface DiscoveriesViewProps {
  deterministic: Recommendation[]
  ai: Recommendation[]
  generatedAt: string | null
}

type DiscoverySource = 'all' | 'ai' | 'deterministic'
type DiscoverySort = 'score' | 'title' | 'year'

export function DiscoveriesView({ deterministic, ai, generatedAt }: DiscoveriesViewProps) {
  const films = useMemo(() => [...ai, ...deterministic], [ai, deterministic])
  const [query, setQuery] = useState('')
  const [source, setSource] = useState<DiscoverySource>('all')
  const [sort, setSort] = useState<DiscoverySort>('score')

  const visibleFilms = useMemo(
    () =>
      films
        .filter(
          (film) =>
            searchFilm(film, query, [film.rationale]) &&
            (source === 'all' || film.source === source),
        )
        .sort((left, right) => {
          if (sort === 'title') return left.title.localeCompare(right.title)
          if (sort === 'year') return (right.year ?? 0) - (left.year ?? 0)
          return right.predictedRating - left.predictedRating || left.title.localeCompare(right.title)
        }),
    [films, query, sort, source],
  )

  return (
    <div className="view">
      <PageHeader count={films.length} eyebrow="Beyond the queue" title="Discoveries">
        New directions inferred from the scores, genres, and details that recur across the journal.
      </PageHeader>
      {generatedAt ? (
        <p className="recommendation-date">Last recommendation run: {formatDate(generatedAt, 'full')}</p>
      ) : null}
      <FilterBar
        label="Search discoveries"
        onQueryChange={setQuery}
        query={query}
        resultCount={visibleFilms.length}
        selects={[
          {
            id: 'discovery-source',
            label: 'Source',
            options: [
              { label: 'All suggestions', value: 'all' },
              { label: 'AI picks', value: 'ai' },
              { label: 'Taste matches', value: 'deterministic' },
            ],
            value: source,
            onChange: (value) => setSource(value as DiscoverySource),
          },
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
            <DiscoveryCard discovery={film} key={`${film.source}-${film.tmdbId}`} />
          ))}
        </div>
      ) : (
        <EmptyState title={films.length === 0 ? 'No discoveries published' : 'No films found'}>
          {films.length === 0
            ? 'Run the local recommendation command to create the first set.'
            : 'Try another search or recommendation source.'}
        </EmptyState>
      )}
    </div>
  )
}
