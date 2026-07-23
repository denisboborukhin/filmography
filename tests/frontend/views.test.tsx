// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { DiscoveriesView } from '../../src/views/DiscoveriesView'
import { DashboardView } from '../../src/views/DashboardView'
import { WatchedView } from '../../src/views/WatchedView'
import { WatchlistView } from '../../src/views/WatchlistView'
import { snapshotFixture } from './fixtures'

afterEach(cleanup)

describe('journal views', () => {
  it('searches the watched archive across review content', async () => {
    const user = userEvent.setup()
    render(<WatchedView films={snapshotFixture.watched} />)

    await user.type(screen.getByRole('searchbox'), 'dreamlike')

    expect(screen.getByRole('heading', { name: 'Spirited Away' })).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: 'Eternal Sunshine of the Spotless Mind' }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('1 film')).toBeInTheDocument()
  })

  it('hides dismissed watchlist entries', () => {
    render(<WatchlistView films={snapshotFixture.watchlist} />)

    expect(screen.getByRole('heading', { name: 'Howl’s Moving Castle' })).toBeInTheDocument()
    expect(screen.queryByText('Dismissed Film')).not.toBeInTheDocument()
  })

  it('shows personal and TMDB scores in the watched archive', () => {
    render(<WatchedView films={snapshotFixture.watched} />)

    expect(screen.getByLabelText('Watched score legend')).toHaveTextContent('Personal score')
    expect(screen.getByLabelText('Personal score: 9.5 out of 10')).toBeInTheDocument()
    expect(screen.getByLabelText('Personal score: 8.0 out of 10')).toBeInTheDocument()
    expect(screen.getByLabelText('TMDB audience score: 8.5 out of 10')).toBeInTheDocument()
  })

  it('leaves an unwritten review empty instead of substituting catalog text', () => {
    const film = structuredClone(snapshotFixture.watched[0])
    film.review = ''
    render(<WatchedView films={[film]} />)

    expect(screen.queryByText(film.overview)).not.toBeInTheDocument()
    expect(screen.queryByText('No written review was included.')).not.toBeInTheDocument()
  })

  it('links watched cards to their TMDB pages', () => {
    render(<WatchedView films={snapshotFixture.watched} />)

    const titleLink = screen.getByRole('link', { name: 'Spirited Away' })

    expect(titleLink).toHaveAttribute(
      'href',
      'https://www.themoviedb.org/movie/129',
    )
    expect(titleLink.closest('h2')).not.toBeNull()
  })

  it('shows expected personal and TMDB scores in the watchlist', () => {
    render(<WatchlistView films={snapshotFixture.watchlist} />)

    expect(screen.getByLabelText('Watchlist score legend')).toHaveTextContent('Personal expected score')
    expect(screen.getByLabelText('Personal expected score: 9.0 out of 10')).toBeInTheDocument()
    expect(screen.getByLabelText('TMDB audience score: 8.4 out of 10')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Highest expected personal score' })).toBeInTheDocument()
  })

  it('links watchlist cards to their TMDB pages', () => {
    render(<WatchlistView films={snapshotFixture.watchlist} />)

    const titleLink = screen.getByRole('link', { name: 'Howl’s Moving Castle' })

    expect(titleLink).toHaveAttribute(
      'href',
      'https://www.themoviedb.org/movie/4935',
    )
    expect(titleLink.closest('h3')).not.toBeNull()
  })

  it('uses the same compact card structure for dashboard reviews and watchlist entries', () => {
    const { container } = render(<DashboardView snapshot={snapshotFixture} />)

    expect(container.querySelectorAll('.compact-card.review-card--compact')).toHaveLength(2)
    expect(container.querySelectorAll('.compact-card.watchlist-card--compact')).toHaveLength(1)
    expect(container.querySelectorAll('.compact-card .score-pair')).toHaveLength(3)
  })

  it('combines discoveries with AI picks before local taste matches', async () => {
    const user = userEvent.setup()
    render(
      <DiscoveriesView
        ai={snapshotFixture.aiDiscoveries}
        deterministic={snapshotFixture.deterministicDiscoveries}
        generatedAt={snapshotFixture.recommendationsGeneratedAt}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Up' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'My Neighbor Totoro' })).toBeInTheDocument()
    expect(screen.getAllByRole('article').length).toBeGreaterThanOrEqual(7)
    expect(screen.getByLabelText('Genre')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Highest TMDB score' })).toBeInTheDocument()
    expect(within(screen.getAllByRole('article')[0]).getByText('AI pick')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Sort'), 'tmdb')

    expect(within(screen.getAllByRole('article')[0]).getByText('AI pick')).toBeInTheDocument()
  })

  it('filters discoveries by genre', async () => {
    const user = userEvent.setup()
    render(
      <DiscoveriesView
        ai={snapshotFixture.aiDiscoveries}
        deterministic={snapshotFixture.deterministicDiscoveries}
        generatedAt={snapshotFixture.recommendationsGeneratedAt}
      />,
    )

    await user.selectOptions(screen.getByLabelText('Genre'), 'Drama')

    expect(screen.queryByRole('heading', { name: 'Up' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Grave of the Fireflies' })).toBeInTheDocument()
    expect(screen.getByText('Two siblings struggle to survive near the end of war.')).toBeInTheDocument()
    expect(
      screen.queryByText('Your highly rated dreamlike animation suggests a strong match.'),
    ).not.toBeInTheDocument()
  })

  it('labels personal and TMDB scores separately in discoveries', () => {
    render(
      <DiscoveriesView
        ai={snapshotFixture.aiDiscoveries}
        deterministic={snapshotFixture.deterministicDiscoveries}
        generatedAt={snapshotFixture.recommendationsGeneratedAt}
      />,
    )

    expect(screen.getAllByLabelText('Personal expected score: 8.5 out of 10').length).toBeGreaterThan(0)
    expect(screen.getAllByLabelText('TMDB audience score: 8.0 out of 10').length).toBeGreaterThan(0)
    expect(screen.getByLabelText('Discovery score legend')).toHaveTextContent(
      'Personal expected score',
    )
    expect(screen.getByLabelText('Discovery score legend')).toHaveTextContent(
      'TMDB audience score',
    )
    expect(screen.getByText('An old man and a young scout travel by flying house.')).toBeInTheDocument()
    expect(screen.queryByText(/Suggested by example-model/i)).not.toBeInTheDocument()
  })

  it('links discovery cards to their TMDB pages', () => {
    render(
      <DiscoveriesView
        ai={snapshotFixture.aiDiscoveries}
        deterministic={snapshotFixture.deterministicDiscoveries}
        generatedAt={snapshotFixture.recommendationsGeneratedAt}
      />,
    )

    const titleLink = screen.getByRole('link', { name: 'Up' })

    expect(titleLink).toHaveAttribute(
      'href',
      'https://www.themoviedb.org/movie/14160',
    )
    expect(titleLink.closest('h3')).not.toBeNull()
  })
})
