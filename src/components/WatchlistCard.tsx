import type { WatchlistFilm } from '../domain/snapshot'
import { FilmMeta } from './FilmMeta'
import { Poster } from './Poster'
import { Score } from './Score'

interface WatchlistCardProps {
  film: WatchlistFilm
  compact?: boolean
}

export function WatchlistCard({ film, compact = false }: WatchlistCardProps) {
  return (
    <article className={`watchlist-card ${compact ? 'watchlist-card--compact' : ''}`}>
      <Poster path={film.posterUrl} size={compact ? 'small' : 'medium'} title={film.title} />
      <div className="watchlist-card__body">
        <div className="watchlist-card__heading">
          <div>
            <h3>{film.title}</h3>
            <FilmMeta genres={film.genres} limit={compact ? 1 : 2} year={film.year} />
          </div>
          <Score label="Interest" quiet value={film.interest} />
        </div>
        {!compact && film.overview ? <p className="line-clamp-3">{film.overview}</p> : null}
        {film.notes ? <p className="watchlist-card__note">{film.notes}</p> : null}
        {!compact && film.tags.length > 0 ? (
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
