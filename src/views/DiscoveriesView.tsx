import { useMemo } from 'react'
import type { Recommendation } from '../domain/snapshot'
import { DiscoveryCard } from '../components/DiscoveryCard'
import { EmptyState } from '../components/EmptyState'
import { FilmListControls } from '../components/FilmListControls'
import { PageHeader } from '../components/PageHeader'
import { RatingLegend } from '../components/RatingLegend'
import { useFilmList } from '../hooks/useFilmList'
import { filmKey } from '../lib/filmList'
import { formatDate } from '../lib/format'

interface DiscoveriesViewProps {
  deterministic: Recommendation[]
  ai: Recommendation[]
  generatedAt: string | null
}

const discoverySearchText = (film: Recommendation) => [film.rationale]
const discoveryScore = (film: Recommendation) => film.predictedRating
const discoveryPriority = (film: Recommendation) => (film.source === 'ai' ? 0 : 1)

export function DiscoveriesView({ deterministic, ai, generatedAt }: DiscoveriesViewProps) {
  const films = useMemo(() => [...ai, ...deterministic], [ai, deterministic])
  const { genre, genres, query, setGenre, setQuery, setSort, sort, visibleFilms } = useFilmList(
    films,
    discoverySearchText,
    discoveryScore,
    discoveryPriority,
  )

  return (
    <div className="view">
      <PageHeader count={films.length} eyebrow="Beyond the queue" title="Discoveries">
        AI picks first, then local taste matches from scores, genres, tags, and TMDB metadata.
      </PageHeader>
      {generatedAt ? (
        <p className="recommendation-date">Last recommendation run: {formatDate(generatedAt, 'full')}</p>
      ) : null}
      <RatingLegend label="Discovery score legend" primaryLabel="Personal expected score" />
      <FilmListControls
        genre={genre}
        genres={genres}
        onGenreChange={setGenre}
        onQueryChange={setQuery}
        onSortChange={setSort}
        personalSortLabel="Highest expected personal score"
        query={query}
        resultCount={visibleFilms.length}
        searchLabel="Search discoveries"
        sort={sort}
      />
      {visibleFilms.length > 0 ? (
        <div className="discovery-grid discovery-grid--archive">
          {visibleFilms.map((film) => (
            <DiscoveryCard discovery={film} key={filmKey(film)} />
          ))}
        </div>
      ) : (
        <EmptyState title={films.length === 0 ? 'No discoveries published' : 'No films found'}>
          {films.length === 0
            ? 'Run the recommendation command to publish AI picks and local taste matches.'
            : 'Try another search or genre.'}
        </EmptyState>
      )}
    </div>
  )
}
