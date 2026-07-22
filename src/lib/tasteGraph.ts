import type { WatchedFilm } from '../domain/snapshot'
import { catalogUrl } from './format'
import type { CreditGroup } from './taste'

export const TASTE_GRAPH_WIDTH = 1000
export const TASTE_GRAPH_HEIGHT = 700
const MAX_UNLINKED_COLUMNS = 4
const UNLINKED_SECTION_GAP = 32

export interface TasteGraphPoint {
  x: number
  y: number
}

export interface TasteGraphNode {
  id: string
  kind: 'film' | 'person'
  label: string
  url: string | null
}

export interface TasteGraphLink {
  id: string
  source: string
  target: string
  groups: CreditGroup[]
}

export interface TasteGraphGroup {
  id: string
  kind: 'connected' | 'unlinked'
  nodeIds: string[]
}

export interface TasteGraphLayout {
  groups: TasteGraphGroup[]
  positions: Record<string, TasteGraphPoint>
}

interface ClusterMembers {
  films: TasteGraphNode[]
  id: string
  kind: TasteGraphGroup['kind']
  people: TasteGraphNode[]
}

export function buildTasteGraph(
  films: WatchedFilm[],
  enabledGroups: Set<CreditGroup>,
  actorsPerFilm: number,
) {
  const nodes = new Map<string, TasteGraphNode>()
  const links = new Map<string, TasteGraphLink>()

  films.forEach((film, filmIndex) => {
    const filmId = `film:${film.mediaType}:${film.tmdbId ?? `${film.title}:${film.year ?? filmIndex}`}`
    nodes.set(filmId, {
      id: filmId,
      kind: 'film',
      label: film.title,
      url: catalogUrl(film),
    })

    const groups = [...enabledGroups]
    groups.forEach((group) => {
      const people =
        group === 'cast' ? film.credits.cast.slice(0, actorsPerFilm) : [film.credits.filmmaker]
      people.forEach((person) => {
        if (!person) return
        const personId = `person:${person.tmdbId}`
        nodes.set(personId, {
          id: personId,
          kind: 'person',
          label: person.name,
          url: `https://www.themoviedb.org/person/${person.tmdbId}`,
        })
        const linkId = `${filmId}:${personId}`
        const existing = links.get(linkId)
        if (existing) {
          if (!existing.groups.includes(group)) existing.groups.push(group)
        } else {
          links.set(linkId, { id: linkId, source: filmId, target: personId, groups: [group] })
        }
      })
    })
  })

  const filmsByPerson = linkedFilmsByPerson([...links.values()])
  const recurringPeople = new Set(
    [...filmsByPerson].filter(([, filmIds]) => filmIds.size > 1).map(([personId]) => personId),
  )
  const recurringLinks = [...links.values()].filter((link) => recurringPeople.has(link.target))
  const linkedFilms = new Set(recurringLinks.map((link) => link.source))
  const visibleLinks = [...links.values()].filter(
    (link) => recurringPeople.has(link.target) || !linkedFilms.has(link.source),
  )
  const visiblePeople = new Set(visibleLinks.map((link) => link.target))
  return {
    nodes: [...nodes.values()].filter(
      (node) => node.kind === 'film' || visiblePeople.has(node.id),
    ),
    links: visibleLinks,
  }
}

export function layoutTasteGraph(
  nodes: TasteGraphNode[],
  links: TasteGraphLink[],
): TasteGraphLayout {
  const positions: Record<string, TasteGraphPoint> = {}
  const members = graphComponents(nodes, links)
  const connected = members.filter((member) => member.kind === 'connected')
  const unlinked = members.find((member) => member.kind === 'unlinked')
  placeConnectedGroups(connected, unlinked?.films.length ?? 0, positions)
  if (unlinked) placeUnlinkedFilms(unlinked, links, connected.length > 0, positions)

  return {
    groups: members.map((member) => ({
      id: member.id,
      kind: member.kind,
      nodeIds: [...member.films, ...member.people].map((node) => node.id),
    })),
    positions,
  }
}

function graphComponents(nodes: TasteGraphNode[], links: TasteGraphLink[]): ClusterMembers[] {
  const films = nodes.filter((node) => node.kind === 'film')
  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const recurringPeople = new Set(
    [...linkedFilmsByPerson(links)]
      .filter(([, filmIds]) => filmIds.size > 1)
      .map(([personId]) => personId),
  )
  const connectionLinks = links.filter((link) => recurringPeople.has(link.target))
  const neighbors = new Map<string, Set<string>>()
  connectionLinks.forEach((link) => {
    const sourceNeighbors = neighbors.get(link.source) ?? new Set<string>()
    sourceNeighbors.add(link.target)
    neighbors.set(link.source, sourceNeighbors)
    const targetNeighbors = neighbors.get(link.target) ?? new Set<string>()
    targetNeighbors.add(link.source)
    neighbors.set(link.target, targetNeighbors)
  })

  const remainingFilms = new Set(films.map((film) => film.id))
  const connected: ClusterMembers[] = []
  films
    .filter((film) => neighbors.has(film.id))
    .sort((left, right) => left.label.localeCompare(right.label))
    .forEach((film) => {
      if (!remainingFilms.has(film.id)) return
      const pending = [film.id]
      const visited = new Set<string>()
      while (pending.length > 0) {
        const current = pending.shift()!
        if (visited.has(current)) continue
        visited.add(current)
        const adjacent = [...(neighbors.get(current) ?? [])].sort()
        adjacent.forEach((neighbor) => {
          if (!visited.has(neighbor)) pending.push(neighbor)
        })
      }
      const groupFilms = [...visited]
        .map((id) => nodeById.get(id))
        .filter((node): node is TasteGraphNode => node?.kind === 'film')
      const people = peopleLinkedToFilms(groupFilms, nodeById, links)
      groupFilms.forEach((groupFilm) => remainingFilms.delete(groupFilm.id))
      connected.push({
        id: `connected:${connected.length + 1}`,
        kind: 'connected',
        films: groupFilms,
        people,
      })
    })

  connected.sort(
    (left, right) =>
      right.films.length - left.films.length ||
      left.films[0].label.localeCompare(right.films[0].label),
  )
  const unlinked = films
    .filter((film) => remainingFilms.has(film.id))
    .sort((left, right) => left.label.localeCompare(right.label))
  return [
    ...connected,
    ...(unlinked.length > 0
      ? [
          {
            id: 'unlinked',
            kind: 'unlinked' as const,
            films: unlinked,
            people: peopleLinkedToFilms(unlinked, nodeById, links),
          },
        ]
      : []),
  ]
}

function peopleLinkedToFilms(
  films: TasteGraphNode[],
  nodeById: Map<string, TasteGraphNode>,
  links: TasteGraphLink[],
): TasteGraphNode[] {
  const filmIds = new Set(films.map((film) => film.id))
  return [...new Set(links.filter((link) => filmIds.has(link.source)).map((link) => link.target))]
    .map((id) => nodeById.get(id))
    .filter((node): node is TasteGraphNode => node?.kind === 'person')
    .sort((left, right) => left.label.localeCompare(right.label))
}

function placeConnectedGroups(
  members: ClusterMembers[],
  unlinkedCount: number,
  positions: Record<string, TasteGraphPoint>,
): void {
  if (members.length === 0) return
  const margin = 55
  const unlinkedHeight = unlinkedBandHeight(unlinkedCount)
  const unlinkedGap = unlinkedCount > 0 ? UNLINKED_SECTION_GAP : 0
  const availableHeight = TASTE_GRAPH_HEIGHT - margin * 2 - unlinkedHeight - unlinkedGap
  const columns = Math.min(3, Math.ceil(Math.sqrt(members.length * 1.5)))
  const rows = Math.ceil(members.length / columns)
  const cellWidth = (TASTE_GRAPH_WIDTH - margin * 2) / columns
  const cellHeight = availableHeight / rows

  members.forEach((member, groupIndex) => {
    const column = groupIndex % columns
    const row = Math.floor(groupIndex / columns)
    const centerX = margin + (column + 0.5) * cellWidth
    const centerY = margin + (row + 0.5) * cellHeight
    const radiusX = Math.min(cellWidth * 0.42, 190)
    const radiusY = Math.min(cellHeight * 0.48, 145)
    member.films.forEach((film, filmIndex) => {
      const angle = (filmIndex / member.films.length) * Math.PI * 2 - Math.PI / 2
      positions[film.id] = {
        x: centerX + Math.cos(angle) * radiusX,
        y: centerY + Math.sin(angle) * radiusY,
      }
    })
    placePeopleGrid(member.people, centerX, centerY, cellWidth * 0.7, positions)
  })
}

function placePeopleGrid(
  people: TasteGraphNode[],
  centerX: number,
  centerY: number,
  maxWidth: number,
  positions: Record<string, TasteGraphPoint>,
): void {
  if (people.length === 0) return
  const columns = Math.max(1, Math.ceil(Math.sqrt(people.length)))
  const rows = Math.ceil(people.length / columns)
  const spacingX = Math.min(76, maxWidth / Math.max(columns - 1, 1))
  const spacingY = 58
  people.forEach((person, index) => {
    const column = index % columns
    const row = Math.floor(index / columns)
    positions[person.id] = {
      x: centerX + (column - (columns - 1) / 2) * spacingX,
      y: centerY + (row - (rows - 1) / 2) * spacingY,
    }
  })
}

function placeUnlinkedFilms(
  member: ClusterMembers,
  links: TasteGraphLink[],
  hasConnectedGroups: boolean,
  positions: Record<string, TasteGraphPoint>,
): void {
  const { films } = member
  const margin = 55
  const bandHeight = hasConnectedGroups
    ? unlinkedBandHeight(films.length)
    : TASTE_GRAPH_HEIGHT - margin * 2
  const top = hasConnectedGroups ? TASTE_GRAPH_HEIGHT - margin - bandHeight : margin
  const columns = hasConnectedGroups
    ? Math.min(MAX_UNLINKED_COLUMNS, films.length)
    : Math.max(
        1,
        Math.min(MAX_UNLINKED_COLUMNS, Math.ceil(Math.sqrt(films.length * 1.6))),
      )
  const rows = Math.ceil(films.length / columns)
  const cellWidth = (TASTE_GRAPH_WIDTH - margin * 2) / columns
  const cellHeight = bandHeight / rows
  const personById = new Map(member.people.map((person) => [person.id, person]))
  films.forEach((film, index) => {
    const column = index % columns
    const row = Math.floor(index / columns)
    const centerX = margin + (column + 0.5) * cellWidth
    const centerY = top + (row + 0.5) * cellHeight
    positions[film.id] = { x: centerX, y: centerY }
    const people = links
      .filter((link) => link.source === film.id)
      .map((link) => personById.get(link.target))
      .filter((person): person is TasteGraphNode => person !== undefined)
    const radiusX = Math.min(cellWidth * 0.38, 88)
    const radiusY = Math.min(cellHeight * 0.42, 68)
    people.forEach((person, personIndex) => {
      const angle = (personIndex / people.length) * Math.PI * 2 - Math.PI / 2
      positions[person.id] = {
        x: centerX + Math.cos(angle) * radiusX,
        y: centerY + Math.sin(angle) * radiusY,
      }
    })
  })
}

function unlinkedBandHeight(filmCount: number): number {
  if (filmCount === 0) return 0
  return Math.min(320, Math.ceil(filmCount / MAX_UNLINKED_COLUMNS) * 160)
}

function linkedFilmsByPerson(links: TasteGraphLink[]): Map<string, Set<string>> {
  const result = new Map<string, Set<string>>()
  links.forEach((link) => {
    const films = result.get(link.target) ?? new Set<string>()
    films.add(link.source)
    result.set(link.target, films)
  })
  return result
}
