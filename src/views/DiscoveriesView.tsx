import { useMemo, useState } from 'react'
import type { Recommendation } from '../domain/snapshot'
import { DiscoveryCard } from '../components/DiscoveryCard'
import { EmptyState } from '../components/EmptyState'
import { FilmListControls } from '../components/FilmListControls'
import { PageHeader } from '../components/PageHeader'
import { RatingLegend } from '../components/RatingLegend'
import { compareFilmListItems, type FilmListSort } from '../lib/filmList'
import { formatDate, searchFilm } from '../lib/format'

interface DiscoveriesViewProps {
  deterministic: Recommendation[]
  ai: Recommendation[]
  generatedAt: string | null
}

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
  const [genre, setGenre] = useState('all')
  const [sort, setSort] = useState<FilmListSort>('title')
  const genres = useMemo(
    () => [...new Set(films.flatMap((film) => film.genres))].sort(),
    [films],
  )

  const visibleFilms = useMemo(
    () =>
      films
        .filter(
          (film) =>
            searchFilm(film, query, [film.rationale]) &&
            (genre === 'all' || film.genres.includes(genre)),
        )
        .sort((left, right) =>
          compareFilmListItems(left, right, sort, (film) => film.predictedRating),
        ),
    [films, genre, query, sort],
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
        genreId="discovery-genre"
        genres={genres}
        onGenreChange={setGenre}
        onQueryChange={setQuery}
        onSortChange={setSort}
        personalSortLabel="Highest expected personal score"
        query={query}
        resultCount={visibleFilms.length}
        searchLabel="Search discoveries"
        sort={sort}
        sortId="discovery-sort"
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
            : 'Try another search or genre.'}
        </EmptyState>
      )}
    </div>
  )
}
