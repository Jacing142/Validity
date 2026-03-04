import { ShieldCheck } from 'lucide-react'
import { useVerify } from './hooks/useVerify'
import InputPanel from './components/InputPanel'
import ThoughtPanel from './components/ThoughtPanel'
import VerdictPanel from './components/VerdictPanel'
import ClaimModal from './components/ClaimModal'

export default function App() {
  const { submitText, status, events, verdict, error, hitlClaims, submitHitl } = useVerify()

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck size={22} className="text-blue-600" />
          <span className="text-lg font-bold text-gray-900 tracking-tight">Validity</span>
        </div>
        <span className="text-sm text-gray-400">Agentic claim verification</span>
      </header>

      {/* Main two-panel layout */}
      <main className="flex-1 flex flex-col lg:flex-row gap-4 p-4 min-h-0" style={{ minHeight: 'calc(100vh - 56px)' }}>
        {/* Left panel: Input + Verdict */}
        <div className="flex flex-col gap-4 lg:w-[58%] min-w-0">
          {/* Input section */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <InputPanel onSubmit={submitText} status={status} />
          </div>

          {/* Verdict section */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 flex-1">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Verification Results
            </h2>
            <VerdictPanel verdict={verdict} status={status} error={error} />
          </div>
        </div>

        {/* Right panel: ThoughtPanel */}
        <div className="lg:w-[42%] min-w-0" style={{ minHeight: '500px' }}>
          <ThoughtPanel events={events} status={status} />
        </div>
      </main>

      {/* Phase 3: HITL claim review modal — rendered when pipeline pauses for user input */}
      {hitlClaims && (
        <ClaimModal
          isOpen={!!hitlClaims}
          claims={hitlClaims}
          onConfirm={submitHitl}
        />
      )}
    </div>
  )
}
