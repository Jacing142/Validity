import { useState } from 'react'
import { Plus, CheckSquare, Square, AlertCircle, Edit2, Check } from 'lucide-react'

/**
 * ClaimModal — Phase 3 HITL claim review modal.
 *
 * Props:
 *   claims     — array of claim objects from hitl_request (may include classification, reformulation)
 *   onConfirm  — (approvedClaims: array) => void  — called with full claim objects
 *   isOpen     — boolean
 *
 * For subjective claims (classification === "subjective" && reformulation != null), renders:
 *   - Original text with "Subjective" badge
 *   - Suggested reformulation with three options: Use reformulation / Keep original / Edit
 */
export default function ClaimModal({ claims = [], onConfirm, isOpen }) {
  const [checked, setChecked] = useState(() =>
    Object.fromEntries(claims.map((c) => [c.id, true]))
  )
  const [customText, setCustomText] = useState('')
  const [customClaims, setCustomClaims] = useState([])

  // For subjective claims: track which text option is chosen
  // Options: "reformulation" | "original" | "edit"
  const [reformulationChoice, setReformulationChoice] = useState(() => {
    const choices = {}
    for (const c of claims) {
      if (c.classification === 'subjective' && c.reformulation) {
        choices[c.id] = 'reformulation'
      }
    }
    return choices
  })
  // For "edit" option: track the edited text per claim
  const [editedText, setEditedText] = useState(() => {
    const edits = {}
    for (const c of claims) {
      if (c.classification === 'subjective' && c.reformulation) {
        edits[c.id] = c.reformulation
      }
    }
    return edits
  })

  if (!isOpen) return null

  function toggleClaim(id) {
    setChecked((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  function addCustom() {
    const trimmed = customText.trim()
    if (!trimmed || trimmed.length > 500) return
    const id = crypto.randomUUID()
    setCustomClaims((prev) => [...prev, { id, text: trimmed, importance_score: 1.0 }])
    setChecked((prev) => ({ ...prev, [id]: true }))
    setCustomText('')
  }

  function handleConfirm() {
    const approvedOriginal = claims
      .filter((c) => checked[c.id])
      .map((c) => {
        const copy = { ...c }
        if (c.classification === 'subjective' && c.reformulation) {
          const choice = reformulationChoice[c.id] || 'reformulation'
          if (choice === 'reformulation') {
            copy.text = c.reformulation
          } else if (choice === 'original') {
            copy.text = c.original_text || c.text
          } else if (choice === 'edit') {
            copy.text = editedText[c.id] || c.reformulation
          }
        }
        return copy
      })

    const approvedCustom = customClaims.filter((c) => checked[c.id])
    onConfirm([...approvedOriginal, ...approvedCustom])
  }

  function handleSkipAll() {
    onConfirm(claims)
  }

  const allClaims = [...claims, ...customClaims]
  const approvedCount = allClaims.filter((c) => checked[c.id]).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in">
      {/* Backdrop — no click handler, modal can only be dismissed via buttons */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between p-6 border-b border-gray-100">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Review Claims for Verification</h2>
            <p className="text-sm text-gray-500 mt-1">
              The following claims were extracted from your text. Approve the ones you want verified,
              remove noise, or add claims the AI missed.
            </p>
          </div>
        </div>

        {/* Claims list */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {allClaims.length === 0 && (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <AlertCircle size={16} />
              No claims extracted.
            </div>
          )}

          {allClaims.map((claim) => {
            const isChecked = !!checked[claim.id]
            const isCustom = !claims.some((c) => c.id === claim.id)
            const isSubjective = !isCustom && claim.classification === 'subjective' && claim.reformulation
            const choice = reformulationChoice[claim.id] || 'reformulation'

            return (
              <div
                key={claim.id}
                className={`rounded-lg border transition-colors ${
                  isChecked ? 'border-blue-200 bg-blue-50' : 'border-gray-200 bg-gray-50 opacity-60'
                }`}
              >
                {/* Main row — click to toggle */}
                <div
                  className="flex items-start gap-3 p-3 cursor-pointer"
                  onClick={() => toggleClaim(claim.id)}
                >
                  <span className="mt-0.5 flex-shrink-0">
                    {isChecked
                      ? <CheckSquare size={16} className="text-blue-600" />
                      : <Square size={16} className="text-gray-400" />
                    }
                  </span>
                  <div className="flex-1 min-w-0">
                    {isSubjective ? (
                      <>
                        {/* Original text with Subjective badge */}
                        <div className="flex items-start gap-2 flex-wrap">
                          <p className="text-sm text-gray-600 leading-relaxed line-through decoration-amber-400">
                            {claim.original_text || claim.text}
                          </p>
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800 border border-amber-200 flex-shrink-0">
                            Subjective
                          </span>
                        </div>
                        <p className="text-[11px] text-gray-400 mt-0.5">
                          Importance: {Math.round((claim.importance_score || 0) * 100)}%
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-sm text-gray-800 leading-relaxed">{claim.text}</p>
                        {isCustom ? (
                          <span className="inline-block text-[11px] text-blue-600 bg-blue-100 px-1.5 py-0.5 rounded mt-1 font-medium">
                            Custom
                          </span>
                        ) : (
                          <p className="text-[11px] text-gray-400 mt-0.5">
                            Importance: {Math.round((claim.importance_score || 0) * 100)}%
                          </p>
                        )}
                      </>
                    )}
                  </div>
                </div>

                {/* Reformulation options — only shown for subjective claims */}
                {isSubjective && isChecked && (
                  <div className="px-3 pb-3 pt-0 ml-7 space-y-2" onClick={(e) => e.stopPropagation()}>
                    <p className="text-[11px] text-gray-500 font-medium uppercase tracking-wide">
                      Suggested reformulation
                    </p>

                    {/* Option: Use reformulation */}
                    <label className={`flex items-start gap-2 cursor-pointer p-2 rounded-md border transition-colors ${choice === 'reformulation' ? 'border-blue-300 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'}`}>
                      <input
                        type="radio"
                        name={`reform-${claim.id}`}
                        checked={choice === 'reformulation'}
                        onChange={() => setReformulationChoice((prev) => ({ ...prev, [claim.id]: 'reformulation' }))}
                        className="mt-0.5 flex-shrink-0"
                      />
                      <div>
                        <span className="text-[11px] font-semibold text-blue-700">Use reformulation</span>
                        <p className="text-xs text-gray-700 mt-0.5">{claim.reformulation}</p>
                      </div>
                    </label>

                    {/* Option: Keep original */}
                    <label className={`flex items-center gap-2 cursor-pointer p-2 rounded-md border transition-colors ${choice === 'original' ? 'border-blue-300 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'}`}>
                      <input
                        type="radio"
                        name={`reform-${claim.id}`}
                        checked={choice === 'original'}
                        onChange={() => setReformulationChoice((prev) => ({ ...prev, [claim.id]: 'original' }))}
                        className="flex-shrink-0"
                      />
                      <span className="text-[11px] font-semibold text-gray-600">Keep original</span>
                    </label>

                    {/* Option: Edit */}
                    <label className={`flex items-start gap-2 cursor-pointer p-2 rounded-md border transition-colors ${choice === 'edit' ? 'border-blue-300 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'}`}>
                      <input
                        type="radio"
                        name={`reform-${claim.id}`}
                        checked={choice === 'edit'}
                        onChange={() => setReformulationChoice((prev) => ({ ...prev, [claim.id]: 'edit' }))}
                        className="mt-0.5 flex-shrink-0"
                      />
                      <div className="flex-1 min-w-0">
                        <span className="text-[11px] font-semibold text-gray-600 flex items-center gap-1">
                          <Edit2 size={10} />
                          Edit
                        </span>
                        {choice === 'edit' && (
                          <input
                            type="text"
                            value={editedText[claim.id] || ''}
                            onChange={(e) => setEditedText((prev) => ({ ...prev, [claim.id]: e.target.value }))}
                            className="mt-1 w-full text-xs px-2 py-1 rounded border border-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
                            placeholder="Edit the reformulation…"
                            maxLength={500}
                            onClick={(e) => e.stopPropagation()}
                          />
                        )}
                      </div>
                    </label>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Add custom claim */}
        <div className="px-6 py-3 border-t border-gray-100">
          <div className="flex gap-2">
            <input
              type="text"
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addCustom()}
              placeholder="Add a claim the AI missed…"
              maxLength={500}
              className="flex-1 text-sm px-3 py-2 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={addCustom}
              disabled={!customText.trim()}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium text-gray-700 transition-colors"
            >
              <Plus size={15} />
              Add
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100">
          <span className="text-sm text-gray-500">
            {approvedCount} of {allClaims.length} claim{allClaims.length !== 1 ? 's' : ''} selected
          </span>
          <div className="flex gap-2">
            <button
              onClick={handleSkipAll}
              className="px-4 py-2 rounded-lg border border-gray-200 text-sm font-medium text-gray-600 hover:bg-gray-50"
            >
              Skip Review (verify all)
            </button>
            <button
              onClick={handleConfirm}
              disabled={approvedCount === 0}
              title={approvedCount === 0 ? 'Select at least one claim to verify' : ''}
              className={`px-4 py-2 rounded-lg text-sm font-semibold text-white transition-colors ${
                approvedCount === 0
                  ? 'bg-blue-300 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              Verify {approvedCount > 0 ? `${approvedCount} ` : ''}Selected Claim{approvedCount !== 1 ? 's' : ''}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
