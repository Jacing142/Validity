import { useState, useRef, useCallback } from 'react'

/**
 * useVerify — central state manager for the verification flow.
 *
 * Returns:
 *   submitText(text)  — starts a verification run
 *   status            — "idle" | "running" | "completed" | "error"
 *   events            — array of streaming events (for ThoughtPanel)
 *   verdict           — final OverallVerdict object, null until complete
 *   error             — error string, null if none
 *   runId             — current run UUID, null if idle
 *   hitlClaims        — Phase 3: claims from HITL request (null in Phase 2)
 *   submitHitl(list)  — Phase 3: send approved claims back (no-op in Phase 2)
 */
export function useVerify() {
  const [status, setStatus] = useState('idle')
  const [events, setEvents] = useState([])
  const [verdict, setVerdict] = useState(null)
  const [error, setError] = useState(null)
  const [runId, setRunId] = useState(null)
  const [hitlClaims, setHitlClaims] = useState(null)

  // Use a ref for the WebSocket so we don't re-render on WS state changes
  const wsRef = useRef(null)
  // Track the current run to ignore events from stale runs on re-submit
  const currentRunRef = useRef(null)

  const submitText = useCallback(async (text) => {
    if (!text || !text.trim()) return

    // Close any existing WebSocket from a previous run
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    // Reset state
    setStatus('running')
    setEvents([])
    setVerdict(null)
    setError(null)
    setHitlClaims(null)

    let newRunId
    try {
      // 1. POST to start the run
      const resp = await fetch('/api/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })

      if (!resp.ok) {
        const body = await resp.text()
        throw new Error(`HTTP ${resp.status}: ${body}`)
      }

      const data = await resp.json()
      newRunId = data.run_id
      setRunId(newRunId)
      currentRunRef.current = newRunId

    } catch (err) {
      setError(`Failed to start verification: ${err.message}`)
      setStatus('error')
      return
    }

    // 2. Open WebSocket to stream events
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/verify/${newRunId}/stream`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onmessage = (evt) => {
      // Ignore events from stale runs (user re-submitted)
      if (currentRunRef.current !== newRunId) return

      let event
      try {
        event = JSON.parse(evt.data)
      } catch {
        return
      }

      setEvents((prev) => [...prev, event])

      if (event.type === 'pipeline_complete') {
        setVerdict(event.data || null)
        setStatus('completed')
        ws.close()
      } else if (event.type === 'pipeline_error') {
        setError(event.detail || 'Unknown pipeline error')
        setStatus('error')
        ws.close()
      } else if (event.type === 'hitl_request') {
        // Phase 3: populate HITL claims
        setHitlClaims(event.data?.claims || [])
      }
    }

    ws.onerror = () => {
      if (currentRunRef.current !== newRunId) return
      setError('WebSocket connection error. The server may be unavailable.')
      setStatus('error')
    }

    ws.onclose = (evt) => {
      if (currentRunRef.current !== newRunId) return
      // If we closed while still running, it's an unexpected disconnect
      if (status === 'running') {
        // Check if we already have a terminal status from onmessage
        setStatus((prev) => {
          if (prev === 'running') {
            setError('Connection closed unexpectedly. Try again.')
            return 'error'
          }
          return prev
        })
      }
    }
  }, [])

  // Phase 3: send HITL response back over WebSocket
  const submitHitl = useCallback((approvedClaims) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'hitl_response',
        approved_claims: approvedClaims,
      }))
      setHitlClaims(null)
    }
  }, [])

  return {
    submitText,
    status,
    events,
    verdict,
    error,
    runId,
    hitlClaims,
    submitHitl,
  }
}
