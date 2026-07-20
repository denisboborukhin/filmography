import { useState } from 'react'
import { Film } from 'lucide-react'
import { posterUrl } from '../lib/format'

interface PosterProps {
  path: string | null
  title: string
  eager?: boolean
  size?: 'small' | 'medium' | 'large'
}

export function Poster({ path, title, eager = false, size = 'medium' }: PosterProps) {
  const source = posterUrl(path)
  const [failedSource, setFailedSource] = useState<string | null>(null)
  const failed = source !== null && source === failedSource

  return (
    <div className={`poster poster--${size}`}>
      <div
        aria-hidden={source && !failed ? true : undefined}
        aria-label={!source || failed ? `No poster available for ${title}` : undefined}
        className="poster__fallback"
        role={!source || failed ? 'img' : undefined}
      >
        <Film aria-hidden="true" size={28} strokeWidth={1.5} />
        <span>{title}</span>
      </div>
      {source && !failed ? (
        <img
          alt={`${title} poster`}
          decoding="async"
          loading={eager ? 'eager' : 'lazy'}
          onError={() => setFailedSource(source)}
          src={source}
        />
      ) : null}
    </div>
  )
}
