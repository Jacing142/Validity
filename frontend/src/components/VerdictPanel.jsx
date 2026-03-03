import { useState } from 'react'
import { ChevronDown, ChevronRight, ExternalLink, CheckCircle2, XCircle, MinusCircle, Loader2, AlertTriangle } from 'lucide-react'

/**
 * VerdictPanel — renders the structured verification results.
 *
 * Props:
 *   verdict  — OverallVerdict object, null until complete
 *   status   — "idle" | "running" | "completed" | "error"
 *   error    — error string, null if none
 */

// Color maps for verdict and tier values
const VERDICT_STYLES = {
  high:        { badge: 'bg-emerald-100 text-emerald-800 border-emerald-200', banner: 'from-emerald-50 to-white border-emerald-200', dot: 'bg-emerald-500' },
  medium:      { badge: 'bg-amber-100 text-amber-800 border-amber-200',       banner: 'from-amber-50 to-white border-amber-200',       dot: 'bg-amber-500' },
  low:         { badge: 'bg-red-100 text-red-800 border-red-200',             banner: 'from-red-50 to-white border-red-200',             dot: 'bg-red-500' },
  mixed:       { badge: 'bg-purple-100 text-purple-800 border-purple-200',    banner: 'from-purple-50 to-white border-purple-200',       dot: 'bg-purple-500' },
  contradicted:{ badge: 'bg-red-100 text-red-900 border-red-300',             banner: 'from-red-50 to-white border-red-200',             dot: 'bg-red-600' },
}

const TIER_STYLES = {
  high: 'bg-teal-100 text-teal-800 border border-teal-200',
  mid:  'bg-slate-100 text-slate-700 border border-slate-200',
  low:  'bg-orange-100 text-orange-700 border border-orange-200',
}

function VerdictBadge({ verdict, size = 'sm' }) {
  const styles = VERDICT_STYLES[verdict] || VERDICT_STYLES.medium
  const label = verdict?.toUpperCase() || 'UNKNOWN'
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full border text-${size === 'lg' ? 'sm' : 'xs'} font-bold ${styles.badge}`}>
      {label}
    </span>
  )
}

function TierBadge({ tier }) {
  const style = TIER_STYLES[tier] || TIER_STYLES.low
  return (
    <span className={`inline-flex items-center px-1.5 py-0 rounded text-[10px] font-semibold uppercase ${style}`}>
      {tier}
    </span>
  )
}

function SourceCard({ source }) {
  const url = source?.url || source?.source?.url || ''
  const title = source?.title || source?.source?.title || 'Untitled'
  const tier = source?.source_tier || source?.source?.source_tier || 'low'
  const intent = source?.query_intent || source?.source?.query_intent || ''

  let domain = ''
  try {
    domain = new URL(url).hostname.replace(/^www\./, '')
  } catch {
    domain = url
  }

  return (
    <div className="flex items-start gap-2 py-1.5 border-b border-gray-100 last:border-0">
      <TierBadge tier={tier} />
      {intent && (
        <span className={`text-[10px] font-medium px-1.5 py-0 rounded border ${intent === 'affirm' ? 'border-emerald-200 text-emerald-700 bg-emerald-50' : 'border-rose-200 text-rose-700 bg-rose-50'}`}>
          {intent}
        </span>
      )}
      <div className="flex-1 min-w-0">
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-600 hover:underline flex items-center gap-1 font-medium truncate"
          title={title}
        >
          {title.length > 70 ? title.slice(0, 70) + '…' : title}
          <ExternalLink size={10} className="flex-shrink-0" />
        </a>
        <span className="text-[10px] text-gray-400">{domain}</span>
      </div>
    </div>
  )
}

function EvidenceItem({ assessment }) {
  const isSupport = assessment.assessment === 'supports'
  const isContradict = assessment.assessment === 'contradicts'
  const domain = (() => {
    try { return new URL(assessment.source?.url || '').hostname.replace(/^www\./, '') } catch { return '' }
  })()

  return (
    <div className="flex items-start gap-2 py-1 text-xs text-gray-700">
      {isSupport && <CheckCircle2 size={12} className="text-emerald-500 flex-shrink-0 mt-0.5" />}
      {isContradict && <XCircle size={12} className="text-red-500 flex-shrink-0 mt-0.5" />}
      {!isSupport && !isContradict && <MinusCircle size={12} className="text-gray-400 flex-shrink-0 mt-0.5" />}
      <div>
        {domain && <span className="font-medium text-gray-500 mr-1">{domain}:</span>}
        <span className="text-gray-600">{assessment.reasoning}</span>
      </div>
    </div>
  )
}

function ClaimCard({ claimVerdict }) {
  const [showSources, setShowSources] = useState(false)
  const [showEvidence, setShowEvidence] = useState(false)

  const { claim_text, verdict, confidence, sources = [], supporting_evidence = [], contradicting_evidence = [] } = claimVerdict
  const styles = VERDICT_STYLES[verdict] || VERDICT_STYLES.medium

  return (
    <div className={`rounded-lg border bg-gradient-to-b ${styles.banner} p-4 flex flex-col gap-3`}>
      {/* Claim header */}
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-gray-800 leading-relaxed">{claim_text}</p>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <VerdictBadge verdict={verdict} />
          <span className="text-xs text-gray-500">{Math.round(confidence * 100)}% confidence</span>
        </div>
      </div>

      {/* Sources collapsible */}
      {sources.length > 0 && (
        <div>
          <button
            onClick={() => setShowSources(!showSources)}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 font-medium"
          >
            {showSources ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {sources.length} source{sources.length !== 1 ? 's' : ''}
          </button>
          {showSources && (
            <div className="mt-2 pl-2 border-l-2 border-gray-200">
              {sources.map((s, i) => (
                <SourceCard key={i} source={s} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Evidence collapsible */}
      {(supporting_evidence.length > 0 || contradicting_evidence.length > 0) && (
        <div>
          <button
            onClick={() => setShowEvidence(!showEvidence)}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 font-medium"
          >
            {showEvidence ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            Evidence ({supporting_evidence.length} supporting, {contradicting_evidence.length} contradicting)
          </button>
          {showEvidence && (
            <div className="mt-2 pl-2 border-l-2 border-gray-200 space-y-0.5">
              {supporting_evidence.map((e, i) => <EvidenceItem key={`s${i}`} assessment={e} />)}
              {contradicting_evidence.map((e, i) => <EvidenceItem key={`c${i}`} assessment={e} />)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function VerdictPanel({ verdict, status, error }) {
  if (status === 'idle') {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-gray-400 text-center px-4">
        Submit text to begin verification
      </div>
    )
  }

  if (status === 'running') {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 px-1 py-4">
        <Loader2 size={16} className="animate-spin text-blue-500" />
        Verification in progress…
      </div>
    )
  }

  if (status === 'hitl') {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 px-1 py-4">
        <Loader2 size={16} className="animate-spin text-amber-500" />
        Reviewing claims — pipeline paused…
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 flex items-start gap-3">
        <AlertTriangle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-semibold text-red-800">Verification failed</p>
          <p className="text-xs text-red-600 mt-0.5">{error || 'An unknown error occurred.'}</p>
        </div>
      </div>
    )
  }

  if (!verdict) return null

  const {
    verdict: overallVerdict,
    summary,
    claim_verdicts = [],
    total_claims,
    high_validity_count,
    medium_validity_count,
    low_validity_count,
    contradicted_count,
  } = verdict

  const styles = VERDICT_STYLES[overallVerdict] || VERDICT_STYLES.medium

  return (
    <div className="flex flex-col gap-4">
      {/* Overall verdict banner */}
      <div className={`rounded-xl border bg-gradient-to-b ${styles.banner} p-5`}>
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <p className="text-xs uppercase tracking-widest text-gray-500 font-medium mb-1">Overall Verdict</p>
            <VerdictBadge verdict={overallVerdict} size="lg" />
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-500">{total_claims} claim{total_claims !== 1 ? 's' : ''} verified</p>
          </div>
        </div>

        {summary && (
          <p className="text-sm text-gray-700 leading-relaxed">{summary}</p>
        )}

        {/* Stats row */}
        <div className="flex gap-3 mt-3 flex-wrap">
          {high_validity_count > 0 && (
            <span className="text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-0.5">
              {high_validity_count} high
            </span>
          )}
          {medium_validity_count > 0 && (
            <span className="text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-0.5">
              {medium_validity_count} medium
            </span>
          )}
          {low_validity_count > 0 && (
            <span className="text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded px-2 py-0.5">
              {low_validity_count} low
            </span>
          )}
          {contradicted_count > 0 && (
            <span className="text-xs font-medium text-red-900 bg-red-100 border border-red-300 rounded px-2 py-0.5">
              {contradicted_count} contradicted
            </span>
          )}
        </div>
      </div>

      {/* Per-claim cards */}
      {claim_verdicts.length > 0 && (
        <div className="flex flex-col gap-3">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Per-Claim Results</h3>
          {claim_verdicts.map((cv) => (
            <ClaimCard key={cv.claim_id} claimVerdict={cv} />
          ))}
        </div>
      )}
    </div>
  )
}
