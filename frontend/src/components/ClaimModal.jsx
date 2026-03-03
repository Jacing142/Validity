import { useState } from 'react'
import { X, Plus, CheckSquare, Square, AlertCircle } from 'lucide-react'

/**
 * ClaimModal — Phase 3 HITL claim review modal.
 *
 * Built as a UI component for Phase 3. NOT connected to the pipeline in Phase 2.
 * The modal is never rendered in the normal Phase 2 flow.
 *
 * Props:
 *   claims     — array of { id, text, importance_score } objects
 *   onConfirm  — (approvedClaims: array) => void
 *   onClose    — () => void
 *   isOpen     — boolean
 *
 * TODO: Wire to useVerify's hitlClaims / submitHitl in Phase 3.
 */
export default function ClaimModal({ claims = [], onConfirm, onClose, isOpen }) {
  const [checked, setChecked] = useState(() =>
    Object.fromEntries(claims.map((c) => [c.id, true]))
  )
  const [customText, setCustomText] = useState('')
  const [customClaims, setCustomClaims] = useState([])

  if (!isOpen) return null

  function toggleClaim(id) {
    setChecked((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  function addCustom() {
    const trimmed = customText.trim()
    if (!trimmed) return
    const id = `custom-${Date.now()}`
    setCustomClaims((prev) => [...prev, { id, text: trimmed, importance_score: 0.5 }])
    setChecked((prev) => ({ ...prev, [id]: true }))
    setCustomText('')
  }

  function handleConfirm() {
    const approved = [
      ...claims.filter((c) => checked[c.id]),
      ...customClaims.filter((c) => checked[c.id]),
    ]
    onConfirm(approved)
  }

  const allClaims = [...claims, ...customClaims]
  const approvedCount = allClaims.filter((c) => checked[c.id]).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

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
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 ml-4 flex-shrink-0"
          >
            <X size={20} />
          </button>
        </div>

        {/* Claims list */}
        <div className="flex-1 overflow-y-auto p-6 space-y-2">
          {allClaims.length === 0 && (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <AlertCircle size={16} />
              No claims extracted.
            </div>
          )}

          {allClaims.map((claim) => {
            const isChecked = !!checked[claim.id]
            const isCustom = claim.id.startsWith('custom-')
            return (
              <div
                key={claim.id}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  isChecked
                    ? 'border-blue-200 bg-blue-50'
                    : 'border-gray-200 bg-gray-50 opacity-60'
                }`}
                onClick={() => toggleClaim(claim.id)}
              >
                <span className="mt-0.5 flex-shrink-0">
                  {isChecked
                    ? <CheckSquare size={16} className="text-blue-600" />
                    : <Square size={16} className="text-gray-400" />
                  }
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-800 leading-relaxed">{claim.text}</p>
                  {!isCustom && (
                    <p className="text-[11px] text-gray-400 mt-0.5">
                      Importance: {Math.round(claim.importance_score * 100)}%
                    </p>
                  )}
                  {isCustom && (
                    <p className="text-[11px] text-blue-500 mt-0.5 font-medium">Custom claim</p>
                  )}
                </div>
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
              className="flex-1 text-sm px-3 py-2 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={addCustom}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-sm font-medium text-gray-700 transition-colors"
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
              onClick={onClose}
              className="px-4 py-2 rounded-lg border border-gray-200 text-sm font-medium text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              disabled={approvedCount === 0}
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
