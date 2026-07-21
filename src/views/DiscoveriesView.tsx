import { useMemo, useState } from 'react'
import type { Recommendation } from '../domain/snapshot'
import { DiscoveryCard } from '../components/DiscoveryCard'
import { EmptyState } from '../components/EmptyState'
import { FilterBar } from '../components/FilterBar'
import { PageHeader } from '../components/PageHeader'
import { RatingLegend } from '../components/RatingLegend'
import { formatDate, searchFilm } from '../lib/format'

interface DiscoveriesViewProps {
  deterministic: Recommendation[]
  ai: Recommendation[]
  generatedAt: string | null
}

type DiscoverySource = 'all' | 'ai' | 'deterministic'
type DiscoverySort = 'score' | 'title' | 'year'

export function DiscoveriesView({ deterministic, ai, generatedAt }: DiscoveriesViewProps) {
  const films = useMemo(
    () =>
      [...ai, ...deterministic].filter(
        (film, index, all) =>
          all.findIndex(
            (candidate) =>
              candidate.mediaType === film.mediaType && candidate.tmdbId === film.tmdbId,
          ) === index,
      ),
    [ai, deterministic],
  )
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
          if (left.source !== right.source) return left.source === 'ai' ? -1 : 1
          return right.predictedRating - left.predictedRating || left.title.localeCompare(right.title)
        }),
    [films, query, sort, source],
  )

  return (
    <div className="view">
      <PageHeader count={films.length} eyebrow="Beyond the queue" title="Discoveries">
        AI picks first, then local taste matches from ratings, genres, tags, and TMDB metadata.
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
            id: 'discovery-source',
            label: 'Source',
            options: [
              { label: 'All recommendations', value: 'all' },
              { label: 'AI picks', value: 'ai' },
              { label: 'Local taste matches', value: 'deterministic' },
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
            <DiscoveryCard discovery={film} key={`${film.source}-${film.mediaType}-${film.tmdbId}`} />
          ))}
        </div>
      ) : (
        <EmptyState title={films.length === 0 ? 'No discoveries published' : 'No films found'}>
          {films.length === 0
            ? 'Run the recommendation command to publish AI picks and local taste matches.'
            : 'Try another search or recommendation source.'}
        </EmptyState>
      )}
    </div>
  )
}
