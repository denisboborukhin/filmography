import { CalendarCheck, ExternalLink } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import type { WatchedFilm } from '../domain/snapshot'
import { formatDate } from '../lib/format'
import { FilmMeta } from './FilmMeta'
import { FilmTitleLink } from './FilmTitleLink'
import { Poster } from './Poster'
import { ScorePair } from './ScorePair'

interface ReviewCardProps {
  film: WatchedFilm
  compact?: boolean
}

export function ReviewCard({ film, compact = false }: ReviewCardProps) {
  if (compact) {
    return (
      <article className="compact-card review-card review-card--compact">
        <Poster path={film.posterUrl} size="small" title={film.title} />
        <div className="compact-card__body">
          <div className="compact-card__heading">
            <h3>
              <FilmTitleLink film={film}>{film.title}</FilmTitleLink>
            </h3>
            <FilmMeta genres={film.genres} limit={1} mediaType={film.mediaType} year={film.year} />
          </div>
          <div className="compact-card__footer">
            <ScorePair
              primaryLabel="Personal score"
              primaryValue={film.rating}
              secondaryValue={film.voteAverage}
            />
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
        <ScorePair
          primaryLabel="Personal score"
          primaryValue={film.rating}
          secondaryValue={film.voteAverage}
        />
      </div>
      <div className="review-card__body">
        <header className="review-card__header">
          <div>
            <h2>
              <FilmTitleLink film={film}>{film.title}</FilmTitleLink>
            </h2>
            <FilmMeta genres={film.genres} limit={3} mediaType={film.mediaType} year={film.year} />
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
          ) : null}
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
