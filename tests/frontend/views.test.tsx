// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
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

  it('shows personal and TMDB ratings in the watched archive', () => {
    render(<WatchedView films={snapshotFixture.watched} />)

    expect(screen.getByLabelText('Watched rating legend')).toHaveTextContent('Personal expected rating')
    expect(screen.getByLabelText('Personal expected rating: 9.5 out of 10')).toBeInTheDocument()
    expect(screen.getByLabelText('TMDB audience rating: 8.5 out of 10')).toBeInTheDocument()
  })

  it('shows expected and TMDB ratings in the watchlist', () => {
    render(<WatchlistView films={snapshotFixture.watchlist} />)

    expect(screen.getByLabelText('Watchlist rating legend')).toHaveTextContent('Personal expected rating')
    expect(screen.getByLabelText('Personal expected rating: 9 out of 10')).toBeInTheDocument()
    expect(screen.getByLabelText('TMDB audience rating: 8.4 out of 10')).toBeInTheDocument()
  })

  it('uses the same compact card structure for dashboard reviews and watchlist entries', () => {
    const { container } = render(<DashboardView snapshot={snapshotFixture} />)

    expect(container.querySelectorAll('.compact-card.review-card--compact')).toHaveLength(2)
    expect(container.querySelectorAll('.compact-card.watchlist-card--compact')).toHaveLength(1)
    expect(container.querySelectorAll('.compact-card .score-pair')).toHaveLength(3)
  })

  it('filters discoveries by source', async () => {
    const user = userEvent.setup()
    render(
      <DiscoveriesView
        ai={snapshotFixture.aiDiscoveries}
        deterministic={snapshotFixture.deterministicDiscoveries}
        generatedAt={snapshotFixture.recommendationsGeneratedAt}
      />,
    )

    await user.selectOptions(screen.getByLabelText('Source'), 'deterministic')

    expect(screen.getByRole('heading', { name: 'My Neighbor Totoro' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Up' })).not.toBeInTheDocument()
  })

  it('labels personal and TMDB ratings separately in discoveries', () => {
    render(
      <DiscoveriesView
        ai={snapshotFixture.aiDiscoveries}
        deterministic={snapshotFixture.deterministicDiscoveries}
        generatedAt={snapshotFixture.recommendationsGeneratedAt}
      />,
    )

    expect(screen.getByLabelText('Your predicted rating: 8.5 out of 10')).toBeInTheDocument()
    expect(screen.getByLabelText('TMDB audience rating: 8 out of 10')).toBeInTheDocument()
    expect(screen.getByLabelText('Discovery rating legend')).toHaveTextContent(
      'Personal expected rating',
    )
    expect(screen.getByLabelText('Discovery rating legend')).toHaveTextContent(
      'TMDB audience score',
    )
  })
})
