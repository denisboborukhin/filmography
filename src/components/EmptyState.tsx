import { Clapperboard } from 'lucide-react'

interface EmptyStateProps {
  title: string
  children: React.ReactNode
}

export function EmptyState({ title, children }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <Clapperboard aria-hidden="true" size={30} strokeWidth={1.5} />
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  )
}
