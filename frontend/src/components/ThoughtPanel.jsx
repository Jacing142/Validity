import { useEffect, useRef } from 'react'
import { CheckCircle2, XCircle, Loader2, Terminal, Zap } from 'lucide-react'

/**
 * ThoughtPanel — live streaming agent reasoning log.
 *
 * Props:
 *   events  — array of streaming events from useVerify
 *   status  — "idle" | "running" | "completed" | "error"
 */

// Consistent color per node name so the eye can track which node is active
const NODE_COLORS = {
  pipeline:   'text-gray-400',
  decompose:  'text-violet-400',
  reformulate:'text-pink-400',
  rank:       'text-blue-400',
  query_gen:  'text-cyan-400',
  search:     'text-emerald-400',
  classify:   'text-amber-400',
  weigh:      'text-orange-400',
  verdict:    'text-rose-400',
  synthesize: 'text-purple-400',
}

const NODE_BG = {
  pipeline:   'bg-gray-800',
  decompose:  'bg-violet-900/40',
  reformulate:'bg-pink-900/40',
  rank:       'bg-blue-900/40',
  query_gen:  'bg-cyan-900/40',
  search:     'bg-emerald-900/40',
  classify:   'bg-amber-900/40',
  weigh:      'bg-orange-900/40',
  verdict:    'bg-rose-900/40',
  synthesize: 'bg-purple-900/40',
}

function EventRow({ event }) {
  const node = event.node || 'system'
  const status = event.status || ''
  const detail = event.detail || ''
  const type = event.type || ''

  const nodeColor = NODE_COLORS[node] || 'text-gray-400'
  const nodeBg = NODE_BG[node] || 'bg-gray-800'

  let icon
  if (type === 'pipeline_complete') {
    icon = <CheckCircle2 size={13} className="text-emerald-400 flex-shrink-0 mt-0.5" />
  } else if (type === 'pipeline_error' || status === 'error') {
    icon = <XCircle size={13} className="text-red-400 flex-shrink-0 mt-0.5" />
  } else if (status === 'completed') {
    icon = <CheckCircle2 size={13} className="text-emerald-500 flex-shrink-0 mt-0.5" />
  } else if (status === 'running') {
    icon = <span className="w-2 h-2 rounded-full bg-blue-400 flex-shrink-0 mt-1 animate-pulse" />
  } else {
    icon = <Zap size={13} className="text-gray-500 flex-shrink-0 mt-0.5" />
  }

  const isTerminal = type === 'pipeline_complete' || type === 'pipeline_error'
  const isCompleted = status === 'completed' || isTerminal

  return (
    <div className={`fade-in flex items-start gap-2 px-3 py-1.5 rounded text-xs font-mono ${isCompleted ? nodeBg : ''}`}>
      {icon}
      <span className={`${nodeColor} font-semibold flex-shrink-0 w-20`}>
        [{node}]
      </span>
      <span className={`${isCompleted ? 'text-gray-200' : 'text-gray-400'} leading-relaxed break-all`}>
        {detail}
      </span>
    </div>
  )
}

export default function ThoughtPanel({ events, status }) {
  const scrollRef = useRef(null)
  const isUserScrolledUp = useRef(false)

  // Track user scroll position to decide whether to auto-scroll
  function handleScroll() {
    const el = scrollRef.current
    if (!el) return
    const threshold = 60
    isUserScrolledUp.current = el.scrollHeight - el.scrollTop - el.clientHeight > threshold
  }

  // Auto-scroll to bottom when new events arrive, unless user scrolled up
  useEffect(() => {
    const el = scrollRef.current
    if (!el || isUserScrolledUp.current) return
    el.scrollTop = el.scrollHeight
  }, [events])

  const hasEvents = events.length > 0

  return (
    <div className="flex flex-col h-full bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800 bg-gray-900">
        <Terminal size={15} className="text-gray-400" />
        <span className="text-sm font-semibold text-gray-300">Agent Reasoning</span>
        {status === 'running' && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-blue-400">
            <Loader2 size={11} className="animate-spin" />
            Live
          </span>
        )}
        {status === 'completed' && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-emerald-400">
            <CheckCircle2 size={11} />
            Done
          </span>
        )}
      </div>

      {/* Log area */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto log-scroll py-2 px-1 space-y-0.5"
        style={{ minHeight: 0 }}
      >
        {!hasEvents && status === 'idle' && (
          <div className="flex flex-col items-center justify-center h-full text-gray-600 text-xs font-mono gap-2">
            <Terminal size={24} className="opacity-30" />
            <span>Waiting for a verification run…</span>
          </div>
        )}

        {!hasEvents && status === 'running' && (
          <div className="flex items-center gap-2 px-3 py-2 text-xs font-mono text-gray-500">
            <Loader2 size={12} className="animate-spin" />
            Connecting to agent stream…
          </div>
        )}

        {events.map((event, i) => (
          <EventRow key={i} event={event} />
        ))}
      </div>
    </div>
  )
}
