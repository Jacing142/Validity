# TODO Phase 2: Implement streaming callback handler.
# This module will capture LangGraph node entry/exit events and push
# them to connected WebSocket clients in real time.
#
# Each node will emit structured events:
#   { node: "search", claim_id: "...", status: "searching", detail: "query: '...'" }
#
# The frontend ThoughtPanel will render these as they arrive.
