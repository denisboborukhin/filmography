// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { DiscoveriesView } from '../../src/views/DiscoveriesView'
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
