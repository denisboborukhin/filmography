import { useMemo } from 'react'
import type { WatchlistFilm } from '../domain/snapshot'
import { EmptyState } from '../components/EmptyState'
import { FilmListControls } from '../components/FilmListControls'
import { PageHeader } from '../components/PageHeader'
import { RatingLegend } from '../components/RatingLegend'
import { WatchlistCard } from '../components/WatchlistCard'
import { useFilmList } from '../hooks/useFilmList'
import { filmKey } from '../lib/filmList'

interface WatchlistViewProps {
  films: WatchlistFilm[]
}

const watchlistSearchText = (film: WatchlistFilm) => [...film.tags, film.notes]
const watchlistScore = (film: WatchlistFilm) => film.interest

export function WatchlistView({ films }: WatchlistViewProps) {
  const activeFilms = useMemo(() => films.filter((film) => !film.dismissed), [films])
  const { genre, genres, query, setGenre, setQuery, setSort, sort, visibleFilms } = useFilmList(
    activeFilms,
    watchlistSearchText,
    watchlistScore,
  )

  return (
    <div className="view">
      <PageHeader count={activeFilms.length} eyebrow="For another evening" title="Watchlist">
        A considered queue, ordered by how strongly each film is calling right now.
      </PageHeader>
      <RatingLegend label="Watchlist score legend" primaryLabel="Personal expected score" />
      <FilmListControls
        genre={genre}
        genres={genres}
        onGenreChange={setGenre}
        onQueryChange={setQuery}
        onSortChange={setSort}
        personalSortLabel="Highest expected personal score"
        query={query}
        resultCount={visibleFilms.length}
        searchLabel="Search the watchlist"
        sort={sort}
      />
      {visibleFilms.length > 0 ? (
        <div className="watchlist-grid">
          {visibleFilms.map((film) => (
            <WatchlistCard film={film} key={filmKey(film)} />
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
