import type { PersonCredit, WatchedFilm } from '../domain/snapshot'

export type CreditGroup = 'cast' | 'filmmaker'

export interface PersonAppearance {
  film: WatchedFilm
  role: string | null
}

export interface FavoritePerson {
  person: PersonCredit
  appearances: PersonAppearance[]
  averagePersonalScore: number
  affinity: number
}

export interface TasteProfile {
  cast: FavoritePerson[]
  filmmakers: FavoritePerson[]
}

export function buildTasteProfile(films: WatchedFilm[]): TasteProfile {
  return {
    cast: rankPeople(films, 'cast'),
    filmmakers: rankPeople(films, 'filmmaker'),
  }
}

function rankPeople(films: WatchedFilm[], group: CreditGroup): FavoritePerson[] {
  const people = new Map<number, { person: PersonCredit; appearances: PersonAppearance[] }>()

  films.forEach((film) => {
    const credits = group === 'cast' ? film.credits.cast : [film.credits.filmmaker].filter(Boolean)
    credits.forEach((person) => {
      if (!person) return
      const existing = people.get(person.tmdbId) ?? { person, appearances: [] }
      existing.appearances.push({ film, role: person.role })
      people.set(person.tmdbId, existing)
    })
  })

  return [...people.values()]
    .map(({ person, appearances }) => {
      const averagePersonalScore =
        appearances.reduce((sum, appearance) => sum + appearance.film.rating, 0) /
        appearances.length
      return {
        person,
        appearances,
        averagePersonalScore,
        affinity: Math.min(10, averagePersonalScore + Math.log2(appearances.length) * 1.25),
      }
    })
    .sort(
      (left, right) =>
        right.affinity - left.affinity ||
        right.appearances.length - left.appearances.length ||
        left.person.name.localeCompare(right.person.name),
    )
}
