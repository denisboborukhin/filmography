import { Score } from './Score'

interface ScorePairProps {
  primaryLabel: string
  primaryValue: number | null
  secondaryLabel?: string
  secondaryValue: number | null
}

export function ScorePair({
  primaryLabel,
  primaryValue,
  secondaryLabel = 'TMDB audience score',
  secondaryValue,
}: ScorePairProps) {
  return (
    <span className="score-pair">
      <Score label={primaryLabel} value={primaryValue} />
      <Score label={secondaryLabel} quiet value={secondaryValue} />
    </span>
  )
}
