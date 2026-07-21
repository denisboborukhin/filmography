import { CalendarDays } from 'lucide-react'

interface FilmMetaProps {
  year: number | null
  genres: string[]
  mediaType?: 'movie' | 'tv'
  limit?: number
}

export function FilmMeta({ year, genres, mediaType = 'movie', limit = 2 }: FilmMetaProps) {
  return (
    <div className="film-meta">
      {mediaType === 'tv' ? <span className="film-meta__media">Series</span> : null}
      {year ? (
        <span>
          <CalendarDays aria-hidden="true" size={14} />
          {year}
        </span>
      ) : null}
      {genres.slice(0, limit).map((genre) => (
        <span className="film-meta__genre" key={genre}>
          {genre}
        </span>
      ))}
    </div>
  )
}
