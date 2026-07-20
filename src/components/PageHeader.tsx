interface PageHeaderProps {
  eyebrow: string
  title: string
  children: React.ReactNode
  count?: number
}

export function PageHeader({ eyebrow, title, children, count }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>
          {title}
          {count === undefined ? null : <span className="title-count">{count}</span>}
        </h1>
      </div>
      <p className="page-header__intro">{children}</p>
    </header>
  )
}
