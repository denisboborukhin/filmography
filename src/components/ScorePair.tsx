import { Score } from './Score'

interface ScorePairProps {
  primaryLabel: string
  primaryValue: number | null
  secondaryValue: number | null
}

export function ScorePair({
  primaryLabel,
  primaryValue,
  secondaryValue,
}: ScorePairProps) {
  return (
    <span className="score-pair">
      <Score label={primaryLabel} value={primaryValue} />
      <Score label="TMDB audience score" quiet value={secondaryValue} />
    </span>
  )
}
