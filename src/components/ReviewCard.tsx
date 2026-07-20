import { CalendarCheck, ExternalLink } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import type { WatchedFilm } from '../domain/snapshot'
import { formatDate } from '../lib/format'
import { FilmMeta } from './FilmMeta'
import { Poster } from './Poster'
import { Score } from './Score'

interface ReviewCardProps {
  film: WatchedFilm
  compact?: boolean
}

export function ReviewCard({ film, compact = false }: ReviewCardProps) {
  if (compact) {
    return (
      <article className="review-card review-card--compact">
        <Poster path={film.posterUrl} size="small" title={film.title} />
        <div className="review-card__compact-body">
          <div>
            <h3>{film.title}</h3>
            <FilmMeta genres={film.genres} limit={1} year={film.year} />
          </div>
          <div className="review-card__compact-bottom">
            <Score label="Rating" value={film.rating} />
            <span>{formatDate(film.watchedAt)}</span>
          </div>
        </div>
      </article>
    )
  }

  return (
    <article className="review-card">
      <div className="review-card__poster-column">
        <Poster path={film.posterUrl} size="medium" title={film.title} />
        <Score label="Rating" value={film.rating} />
      </div>
      <div className="review-card__body">
        <header className="review-card__header">
          <div>
            <h2>{film.title}</h2>
            <FilmMeta genres={film.genres} limit={3} year={film.year} />
          </div>
          <span className="watched-date">
            <CalendarCheck aria-hidden="true" size={16} />
            {formatDate(film.watchedAt)}
          </span>
        </header>

        {film.review ? (
          <div className="markdown review-card__review">
            <ReactMarkdown
              components={{
                a: ({ children, ...props }) => (
                  <a {...props} rel="noreferrer" target="_blank">
                    {children}
                  </a>
                ),
              }}
            >
              {film.review}
            </ReactMarkdown>
          </div>
        ) : film.overview ? (
          <p className="review-card__overview">{film.overview}</p>
        ) : (
          <p className="review-card__overview">No written review was included.</p>
        )}

        <footer className="review-card__footer">
          {film.tags.length > 0 ? (
            <ul aria-label="Tags" className="tag-list">
              {film.tags.map((tag) => (
                <li key={tag}>{tag}</li>
              ))}
            </ul>
          ) : (
            <span />
          )}
          {film.sourceUrl ? (
            <a className="source-link" href={film.sourceUrl} rel="noreferrer" target="_blank">
              Source
              <ExternalLink aria-hidden="true" size={14} />
            </a>
          ) : null}
        </footer>
      </div>
    </article>
  )
}
