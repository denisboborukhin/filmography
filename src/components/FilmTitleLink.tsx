import type { ReactNode } from 'react'
import type { Film } from '../domain/snapshot'
import { catalogUrl } from '../lib/format'

interface FilmTitleLinkProps {
  children: ReactNode
  film: Pick<Film, 'mediaType' | 'tmdbId' | 'title'>
}

export function FilmTitleLink({ children, film }: FilmTitleLinkProps) {
  const url = catalogUrl(film)
  if (!url) return children

  return (
    <a
      className="film-title-link"
      href={url}
      rel="noreferrer"
      target="_blank"
    >
      {children}
    </a>
  )
}
