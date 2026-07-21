import { Score } from './Score'

interface ScorePairProps {
  primaryLabel: string
  primaryValue: number | null
  secondaryLabel?: string
  secondaryValue: number | null
  fixedDecimal?: boolean
}

export function ScorePair({
  primaryLabel,
  primaryValue,
  secondaryLabel = 'TMDB audience rating',
  secondaryValue,
  fixedDecimal = false,
}: ScorePairProps) {
  return (
    <span className="score-pair">
      <Score fixedDecimal={fixedDecimal} label={primaryLabel} value={primaryValue} />
      <Score fixedDecimal={fixedDecimal} label={secondaryLabel} quiet value={secondaryValue} />
    </span>
  )
}
