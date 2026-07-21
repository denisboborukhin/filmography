import { Bot, BrainCircuit } from 'lucide-react'
import type { Recommendation } from '../domain/snapshot'
import { FilmMeta } from './FilmMeta'
import { Poster } from './Poster'
import { ScorePair } from './ScorePair'

interface DiscoveryCardProps {
  discovery: Recommendation
  featured?: boolean
}

export function DiscoveryCard({ discovery, featured = false }: DiscoveryCardProps) {
  const isAi = discovery.source === 'ai'
  const shouldShowOverview =
    discovery.overview &&
    normalizeText(discovery.overview) !== normalizeText(discovery.rationale)

  return (
    <article className={`discovery-card ${featured ? 'discovery-card--featured' : ''}`}>
      <Poster
        eager={featured}
        path={discovery.posterUrl}
        size={featured ? 'large' : 'medium'}
        title={discovery.title}
      />
      <div className="discovery-card__body">
        <div className="discovery-card__topline">
          <span className={`source-label ${isAi ? 'source-label--ai' : ''}`}>
            {isAi ? (
              <Bot aria-hidden="true" size={14} />
            ) : (
              <BrainCircuit aria-hidden="true" size={14} />
            )}
            {isAi ? 'AI pick' : 'Taste match'}
          </span>
          <ScorePair primaryLabel="Your predicted rating" primaryValue={discovery.predictedRating} secondaryValue={discovery.voteAverage} />
        </div>
        <div>
          <h3>{discovery.title}</h3>
          <FilmMeta
            genres={discovery.genres}
            mediaType={discovery.mediaType}
            year={discovery.year}
          />
        </div>
        <p className="discovery-card__reason">{discovery.rationale}</p>
        {shouldShowOverview ? (
          <p className="discovery-card__overview">{discovery.overview}</p>
        ) : null}
      </div>
    </article>
  )
}

function normalizeText(value: string): string {
  return value.toLocaleLowerCase().replace(/\s+/g, ' ').trim()
}
