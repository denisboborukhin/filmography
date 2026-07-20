import { Search } from 'lucide-react'

interface SelectOption {
  label: string
  value: string
}

interface FilterSelect {
  id: string
  label: string
  options: SelectOption[]
  value: string
  onChange: (value: string) => void
}

interface FilterBarProps {
  label: string
  query: string
  onQueryChange: (value: string) => void
  resultCount: number
  selects: FilterSelect[]
}

export function FilterBar({
  label,
  query,
  onQueryChange,
  resultCount,
  selects,
}: FilterBarProps) {
  return (
    <div className="filter-bar">
      <label className="search-field">
        <span className="sr-only">{label}</span>
        <Search aria-hidden="true" size={18} />
        <input
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={label}
          type="search"
          value={query}
        />
      </label>
      <div className="filter-bar__selects">
        {selects.map((select) => (
          <label className="select-field" key={select.id}>
            <span>{select.label}</span>
            <select
              id={select.id}
              onChange={(event) => select.onChange(event.target.value)}
              value={select.value}
            >
              {select.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <p aria-live="polite" className="result-count">
        {resultCount} {resultCount === 1 ? 'film' : 'films'}
      </p>
    </div>
  )
}
