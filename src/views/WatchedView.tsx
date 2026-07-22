import type { WatchedFilm } from '../domain/snapshot'
import { EmptyState } from '../components/EmptyState'
import { FilmListControls } from '../components/FilmListControls'
import { PageHeader } from '../components/PageHeader'
import { RatingLegend } from '../components/RatingLegend'
import { ReviewCard } from '../components/ReviewCard'
import { useFilmList } from '../hooks/useFilmList'
import { filmKey } from '../lib/filmList'

interface WatchedViewProps {
  films: WatchedFilm[]
}

const watchedSearchText = (film: WatchedFilm) => [...film.tags, film.review]
const watchedScore = (film: WatchedFilm) => film.rating

export function WatchedView({ films }: WatchedViewProps) {
  const { genre, genres, query, setGenre, setQuery, setSort, sort, visibleFilms } = useFilmList(
    films,
    watchedSearchText,
    watchedScore,
  )

  return (
    <div className="view">
      <PageHeader count={films.length} eyebrow="The archive" title="Watched">
        Every score and note, from fleeting impressions to the films that refused to leave.
      </PageHeader>
      <RatingLegend label="Watched score legend" primaryLabel="Personal score" />
      <FilmListControls
        genre={genre}
        genres={genres}
        onGenreChange={setGenre}
        onQueryChange={setQuery}
        onSortChange={setSort}
        personalSortLabel="Highest personal score"
        query={query}
        resultCount={visibleFilms.length}
        searchLabel="Search reviews, titles, or tags"
        sort={sort}
      />
      {visibleFilms.length > 0 ? (
        <div className="review-list">
          {visibleFilms.map((film) => (
            <ReviewCard film={film} key={filmKey(film)} />
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
