import { Star } from 'lucide-react'
import { formatScore } from '../lib/format'

interface ScoreProps {
  label: string
  value: number | null
  quiet?: boolean
  fixedDecimal?: boolean
}

export function Score({ label, value, quiet = false, fixedDecimal = false }: ScoreProps) {
  const formattedValue = formatScore(value, fixedDecimal)
  return (
    <span
      aria-label={`${label}: ${value === null ? 'not scored' : `${formattedValue} out of 10`}`}
      className={`score ${quiet ? 'score--quiet' : ''}`}
    >
      <Star aria-hidden="true" fill="currentColor" size={14} strokeWidth={1.75} />
      <strong>{formattedValue}</strong>
      <span aria-hidden="true" className="score__out-of">
        /10
      </span>
    </span>
  )
}
