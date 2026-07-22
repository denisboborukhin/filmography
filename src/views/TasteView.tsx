import { Network, Users } from 'lucide-react'
import type { WatchedFilm } from '../domain/snapshot'
import { EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { TasteNetwork } from '../components/TasteNetwork'
import { formatScore } from '../lib/format'
import { buildTasteProfile, type FavoritePerson } from '../lib/taste'

interface TasteViewProps {
  films: WatchedFilm[]
}

export function TasteView({ films }: TasteViewProps) {
  const profile = buildTasteProfile(films)
  const hasCredits = Object.values(profile).some((people) => people.length > 0)

  return (
    <div className="view">
      <PageHeader
        count={films.length}
        eyebrow="Patterns in the journal"
        title="Taste map"
      >
        Recurring collaborators across watched films, weighted by repeat appearances and personal
        scores.
      </PageHeader>

      {!hasCredits ? (
        <div className="section-block">
          <EmptyState title="No people data yet">
            Rebuild the snapshot with TMDB enabled to identify actors and lead filmmakers.
          </EmptyState>
        </div>
      ) : (
        <>
          <section aria-labelledby="favorite-people-heading" className="section-block">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Personal patterns</p>
                <h2 id="favorite-people-heading">Favorite collaborators</h2>
              </div>
              <Users aria-hidden="true" className="section-heading__icon" size={25} />
            </div>
            <div className="favorite-people-grid">
              <FavoritePeopleList label="Actors" people={profile.cast.slice(0, 6)} />
              <FavoritePeopleList label="Filmmakers" people={profile.filmmakers.slice(0, 6)} />
            </div>
          </section>

          <section aria-labelledby="network-heading" className="section-block">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Watched connections</p>
                <h2 id="network-heading">Films and the people behind them</h2>
              </div>
              <Network aria-hidden="true" className="section-heading__icon" size={25} />
            </div>
            <p className="taste-network-intro">
              Nearby films are connected by people who appear in more than one visible title;
              unlinked films keep their own cast around them. Adjust the score and cast-size filters,
              drag nodes to rearrange the map, and select one to open its TMDB page.
            </p>
            <TasteNetwork films={films} />
          </section>
        </>
      )}
    </div>
  )
}

function FavoritePeopleList({ label, people }: { label: string; people: FavoritePerson[] }) {
  return (
    <section className="favorite-people-group">
      <h3>{label}</h3>
      {people.length > 0 ? (
        <ol>
          {people.map((favorite) => (
            <li key={favorite.person.tmdbId}>
              <a
                href={`https://www.themoviedb.org/person/${favorite.person.tmdbId}`}
                rel="noreferrer"
                target="_blank"
              >
                {favorite.person.name}
              </a>
              <span>
                {favorite.appearances.length}{' '}
                {favorite.appearances.length === 1 ? 'title' : 'titles'} · avg{' '}
                {formatScore(favorite.averagePersonalScore)}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p>No {label.toLocaleLowerCase()} found.</p>
      )}
    </section>
  )
}
