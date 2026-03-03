import { useState } from 'react'
import { Search, Loader2 } from 'lucide-react'

/**
 * InputPanel — text input area and submit button.
 *
 * Props:
 *   onSubmit(text) — called when user submits
 *   status         — "idle" | "running" | "completed" | "error"
 */
export default function InputPanel({ onSubmit, status }) {
  const [text, setText] = useState('')
  const [validationError, setValidationError] = useState('')

  const isRunning = status === 'running'

  function handleSubmit(e) {
    e.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) {
      setValidationError('Please paste some text to verify.')
      return
    }
    setValidationError('')
    onSubmit(trimmed)
  }

  return (
    <div className="flex flex-col gap-3">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Text to verify
        </label>
        <textarea
          value={text}
          onChange={(e) => { setText(e.target.value); setValidationError('') }}
          placeholder="Paste a paragraph to verify..."
          rows={7}
          disabled={isRunning}
          className={[
            'w-full px-3 py-2 rounded-lg border text-sm font-sans resize-y',
            'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
            'transition-opacity',
            isRunning
              ? 'bg-gray-50 text-gray-400 border-gray-200 opacity-60 cursor-not-allowed'
              : 'bg-white text-gray-800 border-gray-300',
          ].join(' ')}
        />
        {validationError && (
          <p className="text-xs text-red-500 mt-1">{validationError}</p>
        )}
      </div>

      <button
        onClick={handleSubmit}
        disabled={isRunning}
        className={[
          'flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg',
          'text-sm font-semibold transition-colors',
          isRunning
            ? 'bg-blue-400 text-white cursor-not-allowed'
            : 'bg-blue-600 hover:bg-blue-700 text-white cursor-pointer',
        ].join(' ')}
      >
        {isRunning ? (
          <>
            <Loader2 size={16} className="animate-spin" />
            Verifying…
          </>
        ) : (
          <>
            <Search size={16} />
            Verify Claims
          </>
        )}
      </button>
    </div>
  )
}
