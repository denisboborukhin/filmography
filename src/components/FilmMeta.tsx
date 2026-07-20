import { CalendarDays } from 'lucide-react'

interface FilmMetaProps {
  year: number | null
  genres: string[]
  limit?: number
}

export function FilmMeta({ year, genres, limit = 2 }: FilmMetaProps) {
  return (
    <div className="film-meta">
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
