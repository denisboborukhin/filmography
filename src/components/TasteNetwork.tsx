import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { ExternalLink, RotateCcw } from 'lucide-react'
import type { WatchedFilm } from '../domain/snapshot'
import { formatScore } from '../lib/format'
import type { CreditGroup } from '../lib/taste'
import {
  buildTasteGraph,
  layoutTasteGraph,
  TASTE_GRAPH_HEIGHT,
  TASTE_GRAPH_WIDTH,
  type TasteGraphPoint,
} from '../lib/tasteGraph'

interface TasteNetworkProps {
  films: WatchedFilm[]
}

const groupLabels: Record<CreditGroup, string> = {
  cast: 'Actors',
  filmmaker: 'Filmmakers',
}

export function TasteNetwork({ films }: TasteNetworkProps) {
  const [enabledGroups, setEnabledGroups] = useState<Set<CreditGroup>>(
    () => new Set(['cast', 'filmmaker']),
  )
  const [minimumRating, setMinimumRating] = useState(8)
  const [actorsPerFilm, setActorsPerFilm] = useState(4)
  const [maximumFilms, setMaximumFilms] = useState<number | null>(null)
  const eligibleFilms = useMemo(
    () =>
      films
        .filter((film) => film.rating >= minimumRating)
        .sort(
          (left, right) =>
            right.rating - left.rating || left.title.localeCompare(right.title),
        ),
    [films, minimumRating],
  )
  const filteredFilms = useMemo(
    () => eligibleFilms.slice(0, maximumFilms ?? eligibleFilms.length),
    [eligibleFilms, maximumFilms],
  )
  const displayedMaximum = Math.min(maximumFilms ?? eligibleFilms.length, eligibleFilms.length)
  const graph = useMemo(
    () => buildTasteGraph(filteredFilms, enabledGroups, actorsPerFilm),
    [actorsPerFilm, enabledGroups, filteredFilms],
  )
  const layout = useMemo(
    () => layoutTasteGraph(graph.nodes, graph.links),
    [graph.links, graph.nodes],
  )
  const [positionOverrides, setPositionOverrides] = useState<Record<string, TasteGraphPoint>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const dragging = useRef<{ id: string; pointerId: number } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const position = (id: string) => positionOverrides[id] ?? layout.positions[id]
  const selected = graph.nodes.find((node) => node.id === selectedId) ?? null

  function toggleGroup(group: CreditGroup) {
    setPositionOverrides({})
    setSelectedId(null)
    setEnabledGroups((current) => {
      const next = new Set(current)
      if (next.has(group)) {
        if (next.size > 1) next.delete(group)
      } else {
        next.add(group)
      }
      return next
    })
  }

  function updateMinimumRating(value: number) {
    setMinimumRating(value)
    setPositionOverrides({})
    setSelectedId(null)
  }

  function updateActorsPerFilm(value: number) {
    setActorsPerFilm(value)
    setPositionOverrides({})
    setSelectedId(null)
  }

  function updateMaximumFilms(value: number) {
    setMaximumFilms(value)
    setPositionOverrides({})
    setSelectedId(null)
  }

  function pointFromPointer(event: ReactPointerEvent<SVGGElement>): TasteGraphPoint | null {
    const svg = svgRef.current
    const matrix = svg?.getScreenCTM()
    if (!svg || !matrix) return null
    const point = svg.createSVGPoint()
    point.x = event.clientX
    point.y = event.clientY
    const transformed = point.matrixTransform(matrix.inverse())
    return {
      x: Math.max(34, Math.min(TASTE_GRAPH_WIDTH - 34, transformed.x)),
      y: Math.max(34, Math.min(TASTE_GRAPH_HEIGHT - 34, transformed.y)),
    }
  }

  function startDragging(event: ReactPointerEvent<SVGGElement>, id: string) {
    event.currentTarget.setPointerCapture?.(event.pointerId)
    dragging.current = { id, pointerId: event.pointerId }
    setSelectedId(id)
  }

  function moveNode(event: ReactPointerEvent<SVGGElement>) {
    if (dragging.current?.pointerId !== event.pointerId) return
    const point = pointFromPointer(event)
    if (!point) return
    setPositionOverrides((current) => ({ ...current, [dragging.current!.id]: point }))
  }

  function stopDragging(event: ReactPointerEvent<SVGGElement>) {
    if (dragging.current?.pointerId === event.pointerId) dragging.current = null
  }

  return (
    <div className="taste-network">
      <div className="taste-network__toolbar">
        <div className="taste-network__filters">
          <div aria-label="People shown in the map" className="role-filters">
            {(Object.keys(groupLabels) as CreditGroup[]).map((group) => (
              <button
                aria-pressed={enabledGroups.has(group)}
                key={group}
                onClick={() => toggleGroup(group)}
                type="button"
              >
                {groupLabels[group]}
              </button>
            ))}
          </div>
          <div className="network-range-filters">
            <label>
              <span>
                Minimum personal score <strong>{formatScore(minimumRating)}</strong>
              </span>
              <input
                aria-label="Minimum personal score"
                max="10"
                min="0"
                onChange={(event) => updateMinimumRating(Number(event.currentTarget.value))}
                step="0.1"
                type="range"
                value={minimumRating}
              />
            </label>
            <label>
              <span>
                Actors per film <strong>{actorsPerFilm}</strong>
              </span>
              <input
                aria-label="Actors per film"
                max="12"
                min="1"
                onChange={(event) => updateActorsPerFilm(Number(event.currentTarget.value))}
                step="1"
                type="range"
                value={actorsPerFilm}
              />
            </label>
            <label>
              <span>
                Films shown <strong>{filteredFilms.length}</strong>
              </span>
              <input
                aria-label="Films shown"
                disabled={eligibleFilms.length === 0}
                max={Math.max(1, eligibleFilms.length)}
                min="1"
                onChange={(event) => updateMaximumFilms(Number(event.currentTarget.value))}
                step="1"
                type="range"
                value={Math.max(1, displayedMaximum)}
              />
            </label>
          </div>
        </div>
        <div className="taste-network__actions">
          <span>
            {filteredFilms.length} {filteredFilms.length === 1 ? 'title' : 'titles'}
          </span>
          <button
            className="network-reset"
            onClick={() => setPositionOverrides({})}
            type="button"
          >
            <RotateCcw aria-hidden="true" size={15} />
            Reset positions
          </button>
        </div>
      </div>

      {graph.nodes.length > 0 ? (
        <>
          <div className="taste-network__canvas">
            <svg
              aria-label="Interactive map connecting watched titles with their actors and lead filmmakers"
              ref={svgRef}
              role="group"
              viewBox={`0 0 ${TASTE_GRAPH_WIDTH} ${TASTE_GRAPH_HEIGHT}`}
            >
              <g aria-hidden="true" className="network-links">
                {graph.links.map((link) => {
                  const source = position(link.source)
                  const target = position(link.target)
                  return (
                    <line
                      className={`network-link network-link--${link.groups[0]}`}
                      key={link.id}
                      x1={source.x}
                      x2={target.x}
                      y1={source.y}
                      y2={target.y}
                    />
                  )
                })}
              </g>
              <g className="network-nodes">
                {graph.nodes.map((node) => {
                  const point = position(node.id)
                  const selectedNode = selectedId === node.id
                  return (
                    <g
                      aria-label={`${node.kind === 'film' ? 'Watched title' : 'Person'}: ${node.label}`}
                      aria-pressed={selectedNode}
                      className={`network-node network-node--${node.kind}${selectedNode ? ' network-node--selected' : ''}`}
                      key={node.id}
                      onClick={() => setSelectedId(node.id)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          setSelectedId(node.id)
                        }
                      }}
                      onPointerCancel={stopDragging}
                      onPointerDown={(event) => startDragging(event, node.id)}
                      onPointerMove={moveNode}
                      onPointerUp={stopDragging}
                      role="button"
                      tabIndex={0}
                      transform={`translate(${point.x} ${point.y})`}
                    >
                      <circle r={node.kind === 'film' ? 17 : 10} />
                      <text dy={node.kind === 'film' ? 35 : 27} textAnchor="middle">
                        {shortLabel(node.label)}
                      </text>
                    </g>
                  )
                })}
              </g>
            </svg>
          </div>

          <div aria-live="polite" className="network-selection">
            {selected ? (
              <>
                <div>
                  <span>{selected.kind === 'film' ? 'Watched title' : 'Person'}</span>
                  <strong>{selected.label}</strong>
                </div>
                {selected.url ? (
                  <a href={selected.url} rel="noreferrer" target="_blank">
                    View on TMDB <ExternalLink aria-hidden="true" size={14} />
                  </a>
                ) : null}
              </>
            ) : (
              <p>Select a node for details, or drag it to rearrange the map.</p>
            )}
          </div>
        </>
      ) : (
        <div className="taste-network__empty">
          No watched titles meet the minimum personal score.
        </div>
      )}
    </div>
  )
}

function shortLabel(label: string): string {
  return label.length > 20 ? `${label.slice(0, 18)}…` : label
}
