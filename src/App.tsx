import { useEffect, useRef, useState, type ComponentType } from 'react'
import {
  Aperture,
  Bookmark,
  Clapperboard,
  Compass,
  Eye,
  RefreshCw,
  WifiOff,
  type LucideProps,
} from 'lucide-react'
import { useSnapshot } from './hooks/useSnapshot'
import { formatDate } from './lib/format'
import { DashboardView } from './views/DashboardView'
import { DiscoveriesView } from './views/DiscoveriesView'
import { WatchedView } from './views/WatchedView'
import { WatchlistView } from './views/WatchlistView'

const views = ['dashboard', 'watched', 'watchlist', 'discoveries'] as const
type View = (typeof views)[number]

interface NavigationItem {
  id: View
  label: string
  icon: ComponentType<LucideProps>
}

const navigation: NavigationItem[] = [
  { id: 'dashboard', label: 'Journal', icon: Clapperboard },
  { id: 'watched', label: 'Watched', icon: Eye },
  { id: 'watchlist', label: 'Watchlist', icon: Bookmark },
  { id: 'discoveries', label: 'Discoveries', icon: Compass },
]

function viewFromHash(): View {
  const candidate = window.location.hash.replace(/^#\/?/, '')
  return views.includes(candidate as View) ? (candidate as View) : 'dashboard'
}

function LoadingScreen() {
  return (
    <main className="status-page" id="main-content">
      <div aria-live="polite" className="loading-state" role="status">
        <Aperture aria-hidden="true" className="loading-state__mark" size={34} />
        <p className="eyebrow">Opening the journal</p>
        <h1>Gathering the latest snapshot</h1>
        <div aria-hidden="true" className="loading-lines">
          <span />
          <span />
          <span />
        </div>
      </div>
    </main>
  )
}

interface ErrorScreenProps {
  message: string
  retry: () => void
}

function ErrorScreen({ message, retry }: ErrorScreenProps) {
  return (
    <main className="status-page" id="main-content">
      <div className="error-state" role="alert">
        <WifiOff aria-hidden="true" size={34} strokeWidth={1.5} />
        <p className="eyebrow">Journal unavailable</p>
        <h1>There is no saved edition to show yet.</h1>
        <p>{message}</p>
        <button className="button button--primary" onClick={retry} type="button">
          <RefreshCw aria-hidden="true" size={17} />
          Try again
        </button>
      </div>
    </main>
  )
}

export function App() {
  const { status, result, error, retry } = useSnapshot()
  const [view, setView] = useState<View>(viewFromHash)
  const mainRef = useRef<HTMLElement>(null)
  const isFirstView = useRef(true)

  useEffect(() => {
    const handleHashChange = () => setView(viewFromHash())
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  useEffect(() => {
    document.title = view === 'dashboard' ? 'Filmography' : `${navigation.find((item) => item.id === view)?.label} · Filmography`
    if (isFirstView.current) {
      isFirstView.current = false
    } else {
      mainRef.current?.focus()
    }
  }, [view])

  if (status === 'loading') return <LoadingScreen />
  if (status === 'error') return <ErrorScreen message={error} retry={retry} />

  const { snapshot, warning } = result
  const activeView = (() => {
    if (view === 'watched') return <WatchedView films={snapshot.watched} />
    if (view === 'watchlist') return <WatchlistView films={snapshot.watchlist} />
    if (view === 'discoveries') {
      return (
        <DiscoveriesView
          ai={snapshot.aiDiscoveries}
          generatedAt={snapshot.recommendationsGeneratedAt}
        />
      )
    }
    return <DashboardView snapshot={snapshot} />
  })()

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="site-header">
        <div className="site-header__inner">
          <a aria-label="Filmography home" className="wordmark" href="#dashboard">
            <Aperture aria-hidden="true" size={25} strokeWidth={1.75} />
            <span>Filmography</span>
          </a>
          <nav aria-label="Primary navigation" className="site-nav">
            {navigation.map((item) => {
              const Icon = item.icon
              return (
                <a
                  aria-current={view === item.id ? 'page' : undefined}
                  href={`#${item.id}`}
                  key={item.id}
                >
                  <Icon aria-hidden="true" size={17} />
                  <span>{item.label}</span>
                </a>
              )
            })}
          </nav>
          <p className="edition-date">
            Edition <time dateTime={snapshot.generatedAt}>{formatDate(snapshot.generatedAt)}</time>
          </p>
        </div>
      </header>

      {warning ? (
        <div className="offline-notice" role="status">
          <WifiOff aria-hidden="true" size={16} />
          <span>{warning}</span>
          <button onClick={retry} type="button">
            Refresh
          </button>
        </div>
      ) : null}

      <main className="site-main" id="main-content" ref={mainRef} tabIndex={-1}>
        {activeView}
      </main>

      <footer className="site-footer">
        <div>
          <a className="wordmark wordmark--footer" href="#dashboard">
            <Aperture aria-hidden="true" size={20} />
            Filmography
          </a>
          <p>A static personal film journal, last built {formatDate(snapshot.generatedAt, 'full')}.</p>
        </div>
        <div className="tmdb-credit">
          <a
            aria-label="Visit The Movie Database"
            href="https://www.themoviedb.org"
            rel="noreferrer"
            target="_blank"
          >
            <img
              alt="TMDB"
              height="46"
              src={`${import.meta.env.BASE_URL}tmdb-logo.svg`}
              width="64"
            />
          </a>
          <p className="tmdb-notice">
            Film metadata from TMDB. This product uses the TMDB API but is not endorsed or certified
            by TMDB.
          </p>
        </div>
      </footer>
    </div>
  )
}
