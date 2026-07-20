import { Bot, BrainCircuit } from 'lucide-react'
import type { Recommendation } from '../domain/snapshot'
import { formatDate } from '../lib/format'
import { FilmMeta } from './FilmMeta'
import { Poster } from './Poster'
import { Score } from './Score'

interface DiscoveryCardProps {
  discovery: Recommendation
  featured?: boolean
}

export function DiscoveryCard({ discovery, featured = false }: DiscoveryCardProps) {
  const isAi = discovery.source === 'ai'

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
          <Score label="Predicted rating" value={discovery.predictedRating} />
        </div>
        <div>
          <h3>{discovery.title}</h3>
          <FilmMeta genres={discovery.genres} year={discovery.year} />
        </div>
        <p className="discovery-card__reason">{discovery.rationale}</p>
        {featured && discovery.overview ? (
          <p className="discovery-card__overview">{discovery.overview}</p>
        ) : null}
        {isAi && (discovery.model || discovery.generatedAt) ? (
          <p className="discovery-card__provenance">
            {discovery.model ? `Suggested by ${discovery.model}` : 'AI suggestion'}
            {discovery.generatedAt ? ` · ${formatDate(discovery.generatedAt)}` : ''}
          </p>
        ) : null}
      </div>
    </article>
  )
}
