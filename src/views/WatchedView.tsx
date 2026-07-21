import { useMemo, useState } from 'react'
import type { WatchedFilm } from '../domain/snapshot'
import { EmptyState } from '../components/EmptyState'
import { FilmListControls } from '../components/FilmListControls'
import { PageHeader } from '../components/PageHeader'
import { RatingLegend } from '../components/RatingLegend'
import { ReviewCard } from '../components/ReviewCard'
import { compareFilmListItems, type FilmListSort } from '../lib/filmList'
import { searchFilm } from '../lib/format'

interface WatchedViewProps {
  films: WatchedFilm[]
}

export function WatchedView({ films }: WatchedViewProps) {
  const [query, setQuery] = useState('')
  const [genre, setGenre] = useState('all')
  const [sort, setSort] = useState<FilmListSort>('title')
  const genres = useMemo(
    () => [...new Set(films.flatMap((film) => film.genres))].sort(),
    [films],
  )

  const visibleFilms = useMemo(() => {
    return films
      .filter(
        (film) =>
          searchFilm(film, query, [...film.tags, film.review]) &&
          (genre === 'all' || film.genres.includes(genre)),
      )
      .sort((left, right) => compareFilmListItems(left, right, sort, (film) => film.rating))
  }, [films, genre, query, sort])

  return (
    <div className="view">
      <PageHeader count={films.length} eyebrow="The archive" title="Watched">
        Every score and note, from fleeting impressions to the films that refused to leave.
      </PageHeader>
      <RatingLegend label="Watched score legend" primaryLabel="Personal score" />
      <FilmListControls
        genre={genre}
        genreId="watched-genre"
        genres={genres}
        onGenreChange={setGenre}
        onQueryChange={setQuery}
        onSortChange={setSort}
        personalSortLabel="Highest personal score"
        query={query}
        resultCount={visibleFilms.length}
        searchLabel="Search reviews, titles, or tags"
        sort={sort}
        sortId="watched-sort"
      />
      {visibleFilms.length > 0 ? (
        <div className="review-list">
          {visibleFilms.map((film) => (
            <ReviewCard
              film={film}
              key={`${film.mediaType}-${film.tmdbId ?? film.title}-${film.year}`}
            />
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
