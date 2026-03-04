import { useState } from 'react'
import { CheckCircle2, XCircle, Star, ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react'

/**
 * ClaimModal — Step-by-step HITL wizard. One claim per screen.
 *
 * Props:
 *   claims    — array of claim objects from hitl_request
 *   onConfirm — (approvedClaims: array) => void
 *   isOpen    — boolean
 *
 * decisions[i] = { action: 'confirm'|'remove'|'option', selectedOption: 0|1|2, selectedText: string }
 *   - verifiable default: { action: 'confirm', selectedOption: null, selectedText: claim.text }
 *   - subjective default: { action: 'option', selectedOption: 1, selectedText: reformulation_options[0] }
 *     (selectedOption 0 = original, 1 = cleaner, 2 = quantifiable)
 */
export default function ClaimModal({ claims = [], onConfirm, isOpen }) {
  const [currentStep, setCurrentStep] = useState(0)
  const [decisions, setDecisions] = useState(() =>
    claims.map((claim) => {
      if (claim.claim_type === 'subjective' && claim.reformulation_options?.length >= 1) {
        return { action: 'option', selectedOption: 1, selectedText: claim.reformulation_options[0] }
      }
      return { action: 'confirm', selectedOption: null, selectedText: claim.text }
    })
  )

  if (!isOpen) return null

  const totalSteps = claims.length + 1  // +1 for summary
  const isSummary = currentStep === claims.length
  const progress = (currentStep / totalSteps) * 100

  function setDecision(i, update) {
    setDecisions((prev) => {
      const next = [...prev]
      next[i] = { ...next[i], ...update }
      return next
    })
  }

  function handleSubmit() {
    const approved = []
    claims.forEach((claim, i) => {
      const decision = decisions[i]
      if (decision.action === 'remove') return
      const approvedClaim = { ...claim }
      approvedClaim.text = decision.selectedText
      if (claim.claim_type === 'subjective' && decision.selectedOption === 0) {
        approvedClaim.kept_original_subjective = true
      }
      approved.push(approvedClaim)
    })
    onConfirm(approved)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop — no click-to-dismiss */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* Modal card */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-xl flex flex-col overflow-hidden">

        {/* Progress bar */}
        <div className="h-1 bg-gray-100">
          <div
            className="h-1 bg-blue-500 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Step counter */}
        <div className="flex items-center justify-between px-6 pt-4 pb-2">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
            {isSummary ? 'Review Summary' : `Claim ${currentStep + 1} of ${claims.length}`}
          </span>
          <span className="text-xs text-gray-400">{claims.length} total</span>
        </div>

        {/* Content — keyed for fade-in transition */}
        <div key={currentStep} className="fade-in px-6 pb-4 flex-1">
          {isSummary ? (
            <SummaryStep claims={claims} decisions={decisions} />
          ) : (
            <ClaimStep
              claim={claims[currentStep]}
              decision={decisions[currentStep]}
              onChange={(update) => setDecision(currentStep, update)}
              onNext={() => setCurrentStep((s) => s + 1)}
              isLastClaim={currentStep === claims.length - 1}
            />
          )}
        </div>

        {/* Navigation footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100">
          {/* Back / skip */}
          <div className="flex items-center gap-3">
            {currentStep > 0 && (
              <button
                onClick={() => setCurrentStep((s) => s - 1)}
                className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 font-medium"
              >
                <ChevronLeft size={15} />
                Back
              </button>
            )}
            {!isSummary && (
              <button
                onClick={() => onConfirm(claims)}
                className="text-xs text-gray-400 hover:text-gray-600 underline underline-offset-2"
              >
                Skip review — verify all as-is
              </button>
            )}
          </div>

          {/* Next / Submit — only shown for subjective claims and summary; verifiable claims
              use the combined Confirm & Next button inside ClaimStep */}
          {isSummary ? (
            <button
              onClick={handleSubmit}
              className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors"
            >
              <CheckCircle2 size={15} />
              Continue Verification
            </button>
          ) : claims[currentStep]?.claim_type !== 'verifiable' ? (
            <button
              onClick={() => setCurrentStep((s) => s + 1)}
              className="flex items-center gap-1 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors"
            >
              {currentStep === claims.length - 1 ? 'Review Summary' : 'Next'}
              <ChevronRight size={15} />
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function ClaimStep({ claim, decision, onChange, onNext, isLastClaim }) {
  const isSubjective = claim.claim_type === 'subjective'
  const options = claim.reformulation_options || []

  if (isSubjective) {
    return (
      <div className="flex flex-col gap-4">
        {/* Badge */}
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">
            <AlertTriangle size={11} />
            SUBJECTIVE
          </span>
        </div>

        {/* Original claim */}
        <div>
          <p className="text-xs font-medium text-gray-400 mb-1">Original:</p>
          <p className="text-sm text-gray-600 italic leading-relaxed">"{claim.original_text || claim.text}"</p>
        </div>

        {/* Choice label */}
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Choose a version to verify:</p>

        {/* Option 0: original wording */}
        <OptionCard
          label="Original wording"
          text={claim.original_text || claim.text}
          selected={decision.action === 'option' && decision.selectedOption === 0}
          onSelect={() => onChange({ action: 'option', selectedOption: 0, selectedText: claim.original_text || claim.text })}
        />

        {/* Option 1: cleaner (default, marked with star) */}
        {options.length >= 1 && (
          <OptionCard
            label="Cleaner version"
            text={options[0]}
            selected={decision.action === 'option' && decision.selectedOption === 1}
            onSelect={() => onChange({ action: 'option', selectedOption: 1, selectedText: options[0] })}
            recommended
          />
        )}

        {/* Option 2: quantifiable */}
        {options.length >= 2 && (
          <OptionCard
            label="Quantifiable version"
            text={options[1]}
            selected={decision.action === 'option' && decision.selectedOption === 2}
            onSelect={() => onChange({ action: 'option', selectedOption: 2, selectedText: options[1] })}
          />
        )}

        {/* Remove button */}
        <button
          onClick={() => onChange({ action: 'remove', selectedOption: null, selectedText: '' })}
          className={`flex items-center gap-1.5 self-start px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
            decision.action === 'remove'
              ? 'bg-red-50 border-red-300 text-red-700'
              : 'border-gray-200 text-gray-500 hover:border-red-200 hover:text-red-600 hover:bg-red-50'
          }`}
        >
          <XCircle size={13} />
          Remove this claim
        </button>
      </div>
    )
  }

  // Verifiable claim
  return (
    <div className="flex flex-col gap-4">
      {/* Badge */}
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
          <CheckCircle2 size={11} />
          VERIFIABLE
        </span>
      </div>

      {/* Claim text */}
      <p className="text-base font-medium text-gray-800 leading-relaxed">"{claim.text}"</p>

      {/* Confirm & Next — single primary action */}
      <button
        onClick={() => {
          onChange({ action: 'confirm', selectedOption: null, selectedText: claim.text })
          onNext()
        }}
        className="flex items-center gap-1.5 self-start px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-semibold border border-emerald-500 transition-colors"
      >
        <CheckCircle2 size={14} />
        {isLastClaim ? 'Confirm & Review' : 'Confirm & Next'}
      </button>

      {/* Remove — secondary action, also advances wizard */}
      <button
        onClick={() => {
          onChange({ action: 'remove', selectedOption: null, selectedText: '' })
          onNext()
        }}
        className="flex items-center gap-1.5 self-start px-3 py-1.5 rounded-lg text-xs font-semibold border border-gray-200 text-gray-500 hover:border-red-200 hover:text-red-600 hover:bg-red-50 transition-colors"
      >
        <XCircle size={13} />
        Remove
      </button>
    </div>
  )
}

function OptionCard({ label, text, selected, onSelect, recommended = false }) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left rounded-lg border p-3 transition-colors ${
        selected
          ? 'border-blue-400 bg-blue-50'
          : 'border-gray-200 hover:border-blue-200 hover:bg-gray-50'
      }`}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <span className={`w-3 h-3 rounded-full border-2 flex-shrink-0 ${selected ? 'border-blue-500 bg-blue-500' : 'border-gray-300 bg-white'}`} />
        <span className="text-xs font-semibold text-gray-600">{label}</span>
        {recommended && (
          <span className="flex items-center gap-0.5 ml-auto text-[10px] font-semibold text-amber-600">
            <Star size={9} fill="currentColor" />
            Recommended
          </span>
        )}
      </div>
      <p className="text-sm text-gray-700 leading-relaxed pl-4">{text}</p>
    </button>
  )
}

function SummaryStep({ claims, decisions }) {
  const kept = decisions.filter((d) => d.action !== 'remove').length

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-gray-500 mb-1">
        <span className="font-semibold text-gray-800">{kept}</span> of {claims.length} claims will be verified.
      </p>
      <div className="flex flex-col gap-2 max-h-72 overflow-y-auto pr-1">
        {claims.map((claim, i) => {
          const decision = decisions[i]
          const removed = decision.action === 'remove'
          const reformulated = claim.claim_type === 'subjective' && decision.action === 'option' && decision.selectedOption !== 0

          return (
            <div
              key={claim.id}
              className={`flex items-start gap-2 rounded-lg px-3 py-2 text-sm ${
                removed ? 'bg-gray-50 opacity-50' : 'bg-gray-50'
              }`}
            >
              {removed
                ? <XCircle size={14} className="text-gray-400 flex-shrink-0 mt-0.5" />
                : <CheckCircle2 size={14} className="text-emerald-500 flex-shrink-0 mt-0.5" />
              }
              <div className="flex-1 min-w-0">
                <p className={`leading-snug ${removed ? 'text-gray-400 line-through' : 'text-gray-700'}`}>
                  {removed ? (claim.original_text || claim.text) : decision.selectedText}
                </p>
                {removed && (
                  <span className="text-xs text-gray-400">(removed)</span>
                )}
                {reformulated && (
                  <span className="text-xs text-amber-600 font-medium">⚠ Reformulated from original</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
