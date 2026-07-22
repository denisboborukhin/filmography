// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { snapshotFixture } from './fixtures'
import { TasteView } from '../../src/views/TasteView'
import { buildTasteProfile, type CreditGroup } from '../../src/lib/taste'
import { buildTasteGraph, layoutTasteGraph } from '../../src/lib/tasteGraph'

afterEach(cleanup)

describe('personal taste profile', () => {
  it('ranks recurring people using watched personal scores', () => {
    const profile = buildTasteProfile(snapshotFixture.watched)

    expect(profile.cast[0].person.name).toBe('Favorite Actor')
    expect(profile.cast[0].appearances).toHaveLength(2)
    expect(profile.cast[0].averagePersonalScore).toBe(8.75)
    expect(profile.filmmakers[0].person.name).toBe('Favorite Filmmaker')
  })

  it('renders favorite groups and an interactive TMDB-linked network', async () => {
    const user = userEvent.setup()
    render(<TasteView films={snapshotFixture.watched} />)

    expect(screen.getByRole('heading', { name: /^Taste map/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Favorite collaborators' })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Favorite Actor' })[0]).toHaveAttribute(
      'href',
      'https://www.themoviedb.org/person/1001',
    )
    expect(screen.getByRole('group', { name: /Interactive map/ })).toBeInTheDocument()
    expect(screen.getByLabelText('Minimum personal score')).toHaveValue('8')
    expect(screen.getByLabelText('Actors per film')).toHaveValue('4')
    expect(screen.getByLabelText('Films shown')).toHaveValue('2')

    const filmmakers = screen.getByRole('button', { name: 'Filmmakers' })
    await user.click(filmmakers)
    expect(filmmakers).toHaveAttribute('aria-pressed', 'false')

    await user.click(screen.getByRole('button', { name: 'Person: Favorite Actor' }))
    expect(screen.getByRole('link', { name: /View on TMDB/ })).toHaveAttribute(
      'href',
      'https://www.themoviedb.org/person/1001',
    )
  })

  it('filters map titles by personal score and limits actors per film', () => {
    render(<TasteView films={snapshotFixture.watched} />)

    expect(
      screen.getByRole('button', { name: 'Person: Secondary Shared Actor' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Person: Supporting Actor A' })).toBeNull()
    fireEvent.change(screen.getByLabelText('Actors per film'), { target: { value: '1' } })
    expect(screen.queryByRole('button', { name: 'Person: Secondary Shared Actor' })).toBeNull()

    fireEvent.change(screen.getByLabelText('Minimum personal score'), {
      target: { value: '9' },
    })
    expect(
      screen.getByRole('button', { name: 'Watched title: Spirited Away' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Watched title: Eternal Sunshine of the Spotless Mind' }),
    ).toBeNull()
    expect(screen.getByText('1 title')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Minimum personal score'), {
      target: { value: '10' },
    })
    expect(screen.getByText('No watched titles meet the minimum personal score.')).toBeInTheDocument()
    expect(screen.getByLabelText('Minimum personal score')).toBeInTheDocument()
  })

  it('limits visible films by highest personal score', () => {
    render(<TasteView films={snapshotFixture.watched} />)

    fireEvent.change(screen.getByLabelText('Films shown'), { target: { value: '1' } })

    expect(
      screen.getByRole('button', { name: 'Watched title: Spirited Away' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Watched title: Eternal Sunshine of the Spotless Mind' }),
    ).toBeNull()
    expect(screen.getByText('1 title')).toBeInTheDocument()
  })

  it('clusters connected films in one field and leaves unlinked films standalone', () => {
    const unrelated = structuredClone(snapshotFixture.watched[0])
    unrelated.tmdbId = 999
    unrelated.title = 'Unrelated Film'
    unrelated.credits = {
      cast: [{ tmdbId: 1999, name: 'Unrelated Actor', profileUrl: null, role: null }],
      filmmaker: null,
    }
    const graph = buildTasteGraph(
      [...snapshotFixture.watched, unrelated],
      new Set<CreditGroup>(['cast']),
      1,
    )
    const layout = layoutTasteGraph(graph.nodes, graph.links)
    const spirited = graph.nodes.find((node) => node.label === 'Spirited Away')!
    const eternal = graph.nodes.find(
      (node) => node.label === 'Eternal Sunshine of the Spotless Mind',
    )!
    const unrelatedNode = graph.nodes.find((node) => node.label === 'Unrelated Film')!
    const sharedActor = graph.nodes.find((node) => node.label === 'Favorite Actor')!
    const connected = layout.groups.find((group) => group.kind === 'connected')!
    const unlinked = layout.groups.find((group) => group.kind === 'unlinked')!

    expect(connected.nodeIds).toEqual(
      expect.arrayContaining([spirited.id, eternal.id, sharedActor.id]),
    )
    const unrelatedActor = graph.nodes.find((node) => node.label === 'Unrelated Actor')!
    expect(unlinked.nodeIds).toEqual([unrelatedNode.id, unrelatedActor.id])
    expect(distance(layout.positions[spirited.id], layout.positions[sharedActor.id])).toBeLessThan(
      distance(layout.positions[unrelatedNode.id], layout.positions[sharedActor.id]),
    )
    expect(
      distance(layout.positions[unrelatedNode.id], layout.positions[unrelatedActor.id]),
    ).toBeGreaterThan(60)
  })

  it('renders the actors belonging to an unlinked film', () => {
    render(<TasteView films={[snapshotFixture.watched[0]]} />)

    expect(screen.getByRole('button', { name: 'Person: Favorite Actor' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Person: Supporting Actor A' })).toBeInTheDocument()
  })

  it('assigns separate positions when many people connect the same films', () => {
    const crowded = structuredClone(snapshotFixture.watched[0])
    crowded.credits = {
      cast: Array.from({ length: 12 }, (_, index) => ({
        tmdbId: 2000 + index,
        name: `Actor ${index + 1}`,
        profileUrl: null,
        role: null,
      })),
      filmmaker: null,
    }
    const secondCrowded = structuredClone(crowded)
    secondCrowded.tmdbId = 998
    secondCrowded.title = 'Second Crowded Film'
    const graph = buildTasteGraph([crowded, secondCrowded], new Set<CreditGroup>(['cast']), 12)
    const positions = layoutTasteGraph(graph.nodes, graph.links).positions
    const people = graph.nodes.filter((node) => node.kind === 'person')
    const films = graph.nodes.filter((node) => node.kind === 'film')
    const pairDistances = people.flatMap((person, index) =>
      people.slice(index + 1).map((other) => distance(positions[person.id], positions[other.id])),
    )
    const filmToPersonDistances = films.flatMap((film) =>
      people.map((person) => distance(positions[film.id], positions[person.id])),
    )

    expect(people).toHaveLength(12)
    expect(Math.min(...pairDistances)).toBeGreaterThan(50)
    expect(Math.min(...filmToPersonDistances)).toBeGreaterThan(60)
  })
})

function distance(left: { x: number; y: number }, right: { x: number; y: number }): number {
  return Math.hypot(left.x - right.x, left.y - right.y)
}
