import { FilterBar } from './FilterBar'
import type { FilmListSort } from '../lib/filmList'

interface FilmListControlsProps {
  genre: string
  genres: string[]
  genreId: string
  onGenreChange: (value: string) => void
  onQueryChange: (value: string) => void
  onSortChange: (value: FilmListSort) => void
  personalSortLabel: string
  query: string
  resultCount: number
  searchLabel: string
  sort: FilmListSort
  sortId: string
}

export function FilmListControls({
  genre,
  genres,
  genreId,
  onGenreChange,
  onQueryChange,
  onSortChange,
  personalSortLabel,
  query,
  resultCount,
  searchLabel,
  sort,
  sortId,
}: FilmListControlsProps) {
  return (
    <FilterBar
      label={searchLabel}
      onQueryChange={onQueryChange}
      query={query}
      resultCount={resultCount}
      selects={[
        {
          id: genreId,
          label: 'Genre',
          options: [
            { label: 'All genres', value: 'all' },
            ...genres.map((item) => ({ label: item, value: item })),
          ],
          value: genre,
          onChange: onGenreChange,
        },
        {
          id: sortId,
          label: 'Sort',
          options: [
            { label: 'Title A-Z', value: 'title' },
            { label: 'Newest release', value: 'year' },
            { label: 'Highest TMDB score', value: 'tmdb' },
            { label: personalSortLabel, value: 'personal' },
          ],
          value: sort,
          onChange: (value) => onSortChange(value as FilmListSort),
        },
      ]}
    />
  )
}
