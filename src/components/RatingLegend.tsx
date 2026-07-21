interface RatingLegendProps {
  label: string
  primaryLabel: string
  secondaryLabel?: string
}

export function RatingLegend({
  label,
  primaryLabel,
  secondaryLabel = 'TMDB audience score',
}: RatingLegendProps) {
  return (
    <div aria-label={label} className="rating-legend">
      <span>
        <span
          aria-hidden="true"
          className="rating-legend__swatch rating-legend__swatch--personal"
        />
        {primaryLabel}
      </span>
      <span>
        <span
          aria-hidden="true"
          className="rating-legend__swatch rating-legend__swatch--audience"
        />
        {secondaryLabel}
      </span>
    </div>
  )
}
