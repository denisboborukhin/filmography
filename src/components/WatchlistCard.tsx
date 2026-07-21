import type { WatchlistFilm } from '../domain/snapshot'
import { FilmMeta } from './FilmMeta'
import { Poster } from './Poster'
import { ScorePair } from './ScorePair'

interface WatchlistCardProps {
  film: WatchlistFilm
  compact?: boolean
}

export function WatchlistCard({ film, compact = false }: WatchlistCardProps) {
  if (compact) {
    return (
      <article className="compact-card watchlist-card watchlist-card--compact">
        <Poster path={film.posterUrl} size="small" title={film.title} />
        <div className="compact-card__body">
          <div className="compact-card__heading">
            <h3>{film.title}</h3>
            <FilmMeta genres={film.genres} limit={1} mediaType={film.mediaType} year={film.year} />
          </div>
          <div className="compact-card__footer">
            <ScorePair
              primaryLabel="Personal expected score"
              primaryValue={film.interest}
              secondaryValue={film.voteAverage}
            />
            {film.notes ? <span className="compact-card__note">{film.notes}</span> : null}
          </div>
        </div>
      </article>
    )
  }

  return (
    <article className="watchlist-card">
      <Poster path={film.posterUrl} size="medium" title={film.title} />
      <div className="watchlist-card__body">
        <div className="watchlist-card__heading">
          <div>
            <h3>{film.title}</h3>
            <FilmMeta
              genres={film.genres}
              limit={2}
              mediaType={film.mediaType}
              year={film.year}
            />
          </div>
          <ScorePair
            primaryLabel="Personal expected score"
            primaryValue={film.interest}
            secondaryValue={film.voteAverage}
          />
        </div>
        {film.overview ? <p className="line-clamp-3">{film.overview}</p> : null}
        {film.notes ? <p className="watchlist-card__note">{film.notes}</p> : null}
        {film.tags.length > 0 ? (
          <ul aria-label="Tags" className="tag-list">
            {film.tags.map((tag) => (
              <li key={tag}>{tag}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </article>
  )
}
