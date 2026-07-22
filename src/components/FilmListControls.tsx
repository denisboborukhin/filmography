import { Search } from 'lucide-react'
import type { FilmListSort } from '../lib/filmList'

interface FilmListControlsProps {
  genre: string
  genres: string[]
  onGenreChange: (value: string) => void
  onQueryChange: (value: string) => void
  onSortChange: (value: FilmListSort) => void
  personalSortLabel: string
  query: string
  resultCount: number
  searchLabel: string
  sort: FilmListSort
}

export function FilmListControls({
  genre,
  genres,
  onGenreChange,
  onQueryChange,
  onSortChange,
  personalSortLabel,
  query,
  resultCount,
  searchLabel,
  sort,
}: FilmListControlsProps) {
  return (
    <div className="filter-bar">
      <label className="search-field">
        <span className="sr-only">{searchLabel}</span>
        <Search aria-hidden="true" size={18} />
        <input
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={searchLabel}
          type="search"
          value={query}
        />
      </label>
      <div className="filter-bar__selects">
        <label className="select-field">
          <span>Genre</span>
          <select onChange={(event) => onGenreChange(event.target.value)} value={genre}>
            <option value="all">All genres</option>
            {genres.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="select-field">
          <span>Sort</span>
          <select
            onChange={(event) => onSortChange(event.target.value as FilmListSort)}
            value={sort}
          >
            <option value="title">Title A-Z</option>
            <option value="year">Newest release</option>
            <option value="tmdb">Highest TMDB score</option>
            <option value="personal">{personalSortLabel}</option>
          </select>
        </label>
      </div>
      <p aria-live="polite" className="result-count">
        {resultCount} {resultCount === 1 ? 'film' : 'films'}
      </p>
    </div>
  )
}
