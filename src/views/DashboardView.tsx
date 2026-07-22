import { ArrowRight, Bookmark, Compass, Eye, Star } from 'lucide-react'
import type { FilmographySnapshot } from '../domain/snapshot'
import { DiscoveryCard } from '../components/DiscoveryCard'
import { EmptyState } from '../components/EmptyState'
import { ReviewCard } from '../components/ReviewCard'
import { WatchlistCard } from '../components/WatchlistCard'
import { filmKey } from '../lib/filmList'
import { formatScore } from '../lib/format'

interface DashboardViewProps {
  snapshot: FilmographySnapshot
}

function byDateDescending(left: string | null, right: string | null): number {
  return (right ?? '').localeCompare(left ?? '')
}

export function DashboardView({ snapshot }: DashboardViewProps) {
  const recentReviews = [...snapshot.watched]
    .sort((left, right) => byDateDescending(left.watchedAt, right.watchedAt))
    .slice(0, 3)
  const priorityWatchlist = snapshot.watchlist
    .filter((film) => !film.dismissed)
    .sort((left, right) => (right.interest ?? -1) - (left.interest ?? -1))
    .slice(0, 4)
  const discoveries = [
    ...snapshot.aiDiscoveries,
    ...snapshot.deterministicDiscoveries,
  ]
  const averageRating =
    snapshot.watched.length === 0
      ? null
      : snapshot.watched.reduce((sum, film) => sum + film.rating, 0) / snapshot.watched.length

  return (
    <div className="view">
      <section className="dashboard-hero">
        <div className="dashboard-hero__copy">
          <p className="eyebrow">Personal film journal</p>
          <h1>A record of what stayed with me.</h1>
          <p>
            Reviews, films waiting for the right evening, and fresh ideas shaped by everything I
            have watched so far.
          </p>
          <div className="hero-actions">
            <a className="button button--primary" href="#discoveries">
              Browse discoveries
              <ArrowRight aria-hidden="true" size={17} />
            </a>
            <a className="button button--secondary" href="#watched">
              Read reviews
            </a>
          </div>
        </div>
        <dl className="journal-stats">
          <div>
            <dt>
              <Eye aria-hidden="true" size={17} />
              Watched
            </dt>
            <dd>{snapshot.watched.length}</dd>
          </div>
          <div>
            <dt>
              <Bookmark aria-hidden="true" size={17} />
              Watchlist
            </dt>
            <dd>{snapshot.watchlist.filter((film) => !film.dismissed).length}</dd>
          </div>
          <div>
            <dt>
              <Star aria-hidden="true" size={17} />
              Average
            </dt>
            <dd>{formatScore(averageRating)}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="discovery-heading" className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Suggested next</p>
            <h2 id="discovery-heading">A film worth considering</h2>
          </div>
          <a className="text-link" href="#discoveries">
            All discoveries <ArrowRight aria-hidden="true" size={15} />
          </a>
        </div>
        {discoveries.length > 0 ? (
          <DiscoveryCard discovery={discoveries[0]} featured />
        ) : (
          <EmptyState title="No discoveries yet">
            Run the recommendation command to publish AI picks and local taste matches.
          </EmptyState>
        )}
      </section>

      <div className="dashboard-columns">
        <section aria-labelledby="recent-heading" className="section-block">
          <div className="section-heading section-heading--compact">
            <div>
              <p className="eyebrow">Recently watched</p>
              <h2 id="recent-heading">Latest reviews</h2>
            </div>
            <a aria-label="View all watched films" className="icon-link" href="#watched">
              <ArrowRight aria-hidden="true" size={18} />
            </a>
          </div>
          {recentReviews.length > 0 ? (
            <div className="compact-list">
              {recentReviews.map((film) => (
                <ReviewCard
                  compact
                  film={film}
                  key={filmKey(film)}
                />
              ))}
            </div>
          ) : (
            <EmptyState title="No reviews yet">Imported Markdown reviews will appear here.</EmptyState>
          )}
        </section>

        <section aria-labelledby="watchlist-heading" className="section-block">
          <div className="section-heading section-heading--compact">
            <div>
              <p className="eyebrow">High interest</p>
              <h2 id="watchlist-heading">Watchlist</h2>
            </div>
            <a aria-label="View complete watchlist" className="icon-link" href="#watchlist">
              <ArrowRight aria-hidden="true" size={18} />
            </a>
          </div>
          {priorityWatchlist.length > 0 ? (
            <div className="compact-list">
              {priorityWatchlist.map((film) => (
                <WatchlistCard
                  compact
                  film={film}
                  key={filmKey(film)}
                />
              ))}
            </div>
          ) : (
            <EmptyState title="The watchlist is clear">
              Films from the Markdown watchlist will appear here.
            </EmptyState>
          )}
        </section>
      </div>

      {discoveries.length > 1 ? (
        <section aria-labelledby="more-discoveries-heading" className="section-block">
          <div className="section-heading">
            <div>
              <p className="eyebrow">More directions</p>
              <h2 id="more-discoveries-heading">Continue exploring</h2>
            </div>
            <Compass aria-hidden="true" className="section-heading__icon" size={25} />
          </div>
          <div className="discovery-grid">
            {discoveries.slice(1, 5).map((film) => (
              <DiscoveryCard discovery={film} key={filmKey(film)} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}
