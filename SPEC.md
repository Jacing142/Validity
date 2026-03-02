# VALIDITY — Locked Spec v1

## One Liner

An agentic claim-verification system that decomposes text into atomic claims, retrieves web evidence, tiers sources by credibility, and returns structured verdicts — with full agent reasoning visible in real time.

---

## What This Showcases

| Skill | How It's Used |
|-------|---------------|
| **LangGraph** | Full multi-node agent graph with conditional routing, HITL interrupt, parallel execution, and streaming state updates |
| **LangChain** | LLM abstraction layer, prompt templates, output parsers, configurable model switching |
| **Agentic AI** | Autonomous multi-step reasoning: decompose → decide → search → classify → weigh → synthesize |
| **MCP** | Full pipeline exposed as Claude Desktop callable tools with documented integration |

---

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Agent orchestration | LangGraph | Multi-node graph with HITL, streaming, conditional edges |
| Components | LangChain | LLM abstraction, prompt templates, output parsers |
| Web search | Serper (default) | Fast, cheap, good structured results. Tavily + You.com as documented alts |
| LLM | GPT-4o (default) | Cost-effective for iteration. Anthropic as documented alt |
| Backend | FastAPI | Async-native, WebSocket support, clean API |
| Frontend | Vite + React | Lightweight, fast builds, no unnecessary SSR |
| MCP | FastMCP (Python) | Wraps pipeline as Claude Desktop tool |
| Containerization | Docker Compose | One command to run everything |

---

## Agent Flow (LangGraph)

```
Input: pasted paragraph
  │
  ▼
[Node 1] DECOMPOSE
  LLM extracts all atomic, verifiable claims from the text.
  Non-verifiable statements (opinions, subjective) are tagged and excluded.
  │
  ▼
[Node 2] RANK + FILTER
  LLM ranks claims by verifiability and importance.
  Top N claims selected (configurable, default 5).
  │
  ▼
[HITL] CLAIM REVIEW MODAL
  Pipeline pauses. WebSocket pushes proposed claims to frontend.
  User reviews: ✓ approve / ✗ remove / + add custom claim.
  User confirms → pipeline resumes.
  │
  ▼
[Node 3] GENERATE QUERIES — ADVERSARIAL PAIR (parallel per claim)
  For each claim, LLM generates two sets of search queries:
    AFFIRM:  2-3 queries designed to find supporting evidence
    REFUTE:  2-3 queries designed to find contradicting evidence
  Example for claim "Global GDP grew 3.2% in 2024":
    AFFIRM:  "global GDP growth rate 2024", "world economic growth 2024 data"
    REFUTE:  "global GDP decline 2024", "world economic growth 2024 lower than expected"
  This is a deliberate design choice. It's easy to find agreement online.
  Actively trying to disprove a claim is what makes verification meaningful.
  │
  ▼
[Node 4] WEB SEARCH (parallel per claim, both query sets)
  Serper API (or configured alternative) executes ALL queries (affirm + refute).
  Results tagged with query intent (affirm/refute) for downstream weighing.
  Returns top results with titles, snippets, URLs, and intent tag.
  │
  ▼
[Node 5] SOURCE TIER CLASSIFICATION
  Each source URL classified by credibility tier:
    High:   .gov / .edu / arxiv / pubmed / known peer-reviewed journals
    Mid:    Reuters / BBC / AP / major newspaper domains / .org (established)
    Low:    .com general / vendor blogs / marketing / unknown domains
  Classification is domain-heuristic in v1 (acknowledged in README).
  │
  ▼
[Node 6] EVIDENCE WEIGHING (parallel per claim)
  LLM analyzes each source's content against the claim.
  Classifies as: SUPPORTS / CONTRADICTS / IRRELEVANT.
  Weighs by source tier (High source contradiction > Low source support).
  │
  ▼
[Node 7] VERDICT ASSIGNMENT (per claim)
  Based on weighted evidence:
    HIGH VALIDITY    — strong support from high/mid tier, no contradictions
    MEDIUM VALIDITY  — mixed support, or only low-tier sources
    LOW VALIDITY     — weak/no support, or contradicted by credible sources
    CONTRADICTED     — flag when high-tier sources directly contradict
  │
  ▼
[Node 8] SYNTHESIZE
  Aggregates per-claim verdicts into overall paragraph verdict.
  Weighted by claim importance from Node 2.
  Produces final structured output.
```

---

## HITL — Why It Matters

This isn't a UX feature. It's a named pattern in agentic systems.

**The problem:** An LLM decomposing a paragraph will extract 8-15 claims. Many will be trivial ("The meeting was held on Tuesday"). Verifying all of them wastes search API calls, LLM tokens, and user attention.

**The solution:** The pipeline pauses after decomposition and ranking. The user sees the proposed claims in a modal. They approve the ones worth verifying, remove noise, and optionally add claims the LLM missed. Then the pipeline continues with a focused, user-validated set.

**Implementation:** LangGraph's `interrupt()` function. The graph state is checkpointed. The frontend receives the proposed claims via WebSocket. On user confirmation, the graph resumes from the checkpoint with the updated claim list.

---

## Frontend — Two Panel Layout

### Left Panel (primary)
1. **Input area** — textarea for pasting paragraphs. Submit button.
2. **HITL modal** — fires mid-run after Node 2. Shows ranked claims with approve/remove/add controls. "Continue" button resumes pipeline.
3. **Verdict display** — structured results per claim:
   - Claim text
   - Verdict badge (High / Mid / Low / Contradicted)
   - Sources listed with tier indicator (color-coded)
   - Supporting vs contradicting evidence, one line each
4. **Overall verdict** — aggregated score at top of results

### Right Panel (agent thought stream)
- Real-time feed of every LangGraph node as it fires
- Each entry shows: node name, what it's doing, intermediate results
- Examples: "Decomposing into claims... found 7", "Searching: 'global temperature 2024 data'", "Source classified: nasa.gov → HIGH tier"
- Scrolling log format, newest at bottom
- **This is the demo moment.** A hiring manager watches claims being verified in real time.

### Implementation
- WebSocket connection from frontend to FastAPI
- LangGraph streams state updates via `astream_events()` or custom callbacks
- Each node emits structured events: `{ node: "search", claim_id: 2, status: "searching", detail: "query: 'GDP growth 2024 US'" }`
- Frontend renders these as they arrive

---

## Streaming Architecture

```
LangGraph Node fires
  │
  ▼
Custom callback handler captures node entry/exit + intermediate state
  │
  ▼
FastAPI WebSocket endpoint pushes event to connected client
  │
  ▼
React state updates → ThoughtPanel re-renders
```

**Key decision:** Use LangGraph's callback system, not polling. The frontend opens one WebSocket at run start and receives all updates push-style. No polling, no SSE complexity.

**HITL flow over WebSocket:**
1. Graph hits HITL node → emits `{ type: "hitl_request", claims: [...] }`
2. Frontend shows modal
3. User confirms → frontend sends `{ type: "hitl_response", approved_claims: [...] }` over same WebSocket
4. Backend resumes graph with updated state

---

## MCP Server

### What It Exposes

Three tools:

| Tool | Input | Output |
|------|-------|--------|
| `verify_text` | `{ text: string }` | Full verdict JSON (skips HITL, auto-approves all claims) |
| `verify_text_interactive` | `{ text: string }` | Returns proposed claims first, then accepts approved list |
| `get_run` | `{ run_id: string }` | Retrieves a previous run's results |

### Implementation
- Built with FastMCP (Python)
- Calls the same LangGraph pipeline the web UI uses
- `verify_text` runs the full graph with HITL auto-approved (for non-interactive use)
- `verify_text_interactive` uses MCP's sampling/confirmation pattern for HITL equivalent
- Documented in README with Claude Desktop config JSON and usage GIF

### Claude Desktop Config
```json
{
  "mcpServers": {
    "validity": {
      "command": "python",
      "args": ["-m", "validity.mcp.server"],
      "env": {
        "SEARCH_API_KEY": "your-serper-key",
        "LLM_API_KEY": "your-openai-key"
      }
    }
  }
}
```

---

## API Endpoints

```
POST /api/verify
  Body: { text: string }
  Returns: { run_id: string }
  Starts verification pipeline. Connect to WebSocket for updates.

WS /api/verify/{run_id}/stream
  Streams all node events + HITL request.
  Accepts HITL response from client.

GET /api/verify/{run_id}/result
  Returns final verdict JSON (poll fallback if WebSocket isn't available).

GET /api/health
  Returns { status: "ok", search_provider: "serper", llm_provider: "openai" }
```

---

## Configuration

### `.env.example`
```bash
# LLM Configuration
LLM_PROVIDER=openai                   # openai | anthropic
LLM_API_KEY=sk-...
LLM_MODEL_COMPLEX=gpt-4o             # Complex tasks: decompose, evidence weighing
LLM_MODEL_STANDARD=gpt-4o-mini       # Structured tasks: rank, query gen, verdict, synthesis
# Anthropic equivalents: claude-sonnet-4-20250514 / claude-haiku-4-5-20251001

# Search Configuration
SEARCH_PROVIDER=serper        # serper | tavily | you
SEARCH_API_KEY=...

# Application
MAX_CLAIMS=5                  # Max claims to verify per run
MAX_SOURCES_PER_CLAIM=5       # Max search results per claim
LOG_LEVEL=info
```

### Provider Abstraction
Both LLM and search are behind interfaces. Switching providers is a `.env` change, not a code change.

```python
# LLM — dual model pattern
llm_complex = get_llm(complexity="high")      # decompose, weigh evidence
llm_standard = get_llm(complexity="standard") # rank, query gen, verdict, synthesis

# Search — thin wrapper
search = get_search_client(provider=settings.SEARCH_PROVIDER, api_key=settings.SEARCH_API_KEY)
```

---

## Repo Structure

```
validity/
├── backend/
│   ├── agents/
│   │   ├── graph.py              # LangGraph graph definition + edges
│   │   ├── state.py              # Graph state schema (TypedDict)
│   │   ├── callbacks.py          # Streaming callback handler
│   │   └── nodes/
│   │       ├── decompose.py      # Node 1: extract atomic claims
│   │       ├── rank.py           # Node 2: rank + filter claims
│   │       ├── hitl.py           # HITL: interrupt + resume
│   │       ├── query_gen.py      # Node 3: generate search queries
│   │       ├── search.py         # Node 4: execute web search
│   │       ├── classify.py       # Node 5: source tier classification
│   │       ├── weigh.py          # Node 6: evidence weighing
│   │       ├── verdict.py        # Node 7: per-claim verdict
│   │       └── synthesize.py     # Node 8: overall verdict
│   ├── search/
│   │   ├── base.py               # Abstract search interface
│   │   ├── serper.py             # Serper implementation
│   │   ├── tavily.py             # Tavily implementation
│   │   └── you.py                # You.com implementation
│   ├── config.py                 # Settings from .env
│   ├── models.py                 # Pydantic models for API + state
│   └── main.py                   # FastAPI app + WebSocket + endpoints
├── mcp/
│   └── server.py                 # FastMCP server wrapping pipeline
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── InputPanel.jsx    # Text input + submit
│   │   │   ├── ClaimModal.jsx    # HITL claim review modal
│   │   │   ├── VerdictPanel.jsx  # Per-claim + overall verdicts
│   │   │   └── ThoughtPanel.jsx  # Live agent reasoning stream
│   │   ├── hooks/
│   │   │   └── useVerify.js      # WebSocket connection + state management
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml            # backend + frontend services
├── .env.example
├── Makefile                      # make run, make dev, make test
└── README.md
```

---

## Source Tier Classification — Honest Framing

The v1 source tier system uses domain-based heuristics. This is a deliberate, acknowledged limitation.

**What it does well:**
- `.gov`, `.edu`, `arxiv.org`, `pubmed` → reliably high credibility signals
- Known news wire services (Reuters, AP, AFP) → reliably mid-high
- Marketing/vendor domains → reliably low

**Where it breaks:**
- A `.edu` professor's personal blog ≠ a peer-reviewed paper
- A `.com` investigative journalism piece can be excellent
- Domain age, author credentials, citation count — none of this is captured

**README framing:** "v1 uses domain heuristics for source classification. This is fast and directionally correct for most sources, but doesn't capture nuance. An ML-based credibility classifier is on the v2 roadmap."

---

## LLM Call Map

Every LLM call in the pipeline, what it does, and which model to use.

### Call inventory per run (assuming 5 claims approved)

| Node | Call | What it does | Complexity | Recommended model | Calls per run |
|------|------|-------------|------------|-------------------|---------------|
| Node 1: Decompose | `decompose_claims` | Extract atomic, verifiable claims from input text. Must distinguish facts from opinions. | High — requires nuanced reasoning about what constitutes a verifiable claim | GPT-4o | 1 |
| Node 2: Rank | `rank_claims` | Score claims by verifiability + importance. Select top N. | Medium — ranking against criteria | GPT-4o-mini | 1 |
| Node 3: Query Gen | `generate_queries` | Generate affirm + refute search queries per claim | Medium — needs understanding of claim semantics to write good counter-queries | GPT-4o-mini | 5 (1 per claim) |
| Node 5: Classify | — | Source tier classification | **No LLM call** — pure domain heuristic logic | N/A | 0 |
| Node 6: Weigh | `weigh_evidence` | Read each source snippet, classify as SUPPORTS / CONTRADICTS / IRRELEVANT relative to the claim | High — must understand nuance, partial support, implicit contradiction | GPT-4o | 5 (1 per claim) |
| Node 7: Verdict | `assign_verdict` | Given weighted evidence, assign verdict + confidence | Medium — structured decision from clear inputs | GPT-4o-mini | 5 (1 per claim) |
| Node 8: Synthesize | `synthesize_verdict` | Aggregate per-claim verdicts into overall assessment | Medium — summary + weighting | GPT-4o-mini | 1 |

### Total LLM calls per run: 18

| Model | Calls | Purpose |
|-------|-------|---------|
| GPT-4o | 6 | Decomposition (1) + evidence weighing (5) — the calls where reasoning quality matters most |
| GPT-4o-mini | 12 | Ranking (1) + query gen (5) + verdict (5) + synthesis (1) — structured, lower-complexity tasks |

### Cost estimate per run (5 claims)
- GPT-4o calls: ~6 calls × ~1K tokens avg = ~6K tokens → ~$0.03
- GPT-4o-mini calls: ~12 calls × ~500 tokens avg = ~6K tokens → ~$0.001
- Search API: ~20 queries × $0.001 (Serper) = ~$0.02
- **Total: ~$0.05 per verification run**

### Model selection rationale

**GPT-4o for decomposition:** This is the hardest call in the pipeline. The LLM must read a paragraph, identify every factual claim, separate facts from opinions, and output clean atomic statements. A weaker model produces noisy claims that cascade errors downstream.

**GPT-4o for evidence weighing:** Reading a search snippet and determining if it supports, contradicts, or is irrelevant to a specific claim requires genuine comprehension. Partial support, implicit contradiction, tangential relevance — this is where model quality directly affects verdict accuracy.

**GPT-4o-mini for everything else:** Ranking, query generation, verdict assignment, and synthesis are all structured tasks with clear inputs and constrained outputs. Mini handles these well and keeps costs down.

### Provider switching

When the user sets `LLM_PROVIDER=anthropic`, the model mapping becomes:

| Role | OpenAI | Anthropic |
|------|--------|-----------|
| Complex (decompose, weigh) | GPT-4o | Claude Sonnet 4 |
| Structured (rank, query, verdict, synthesize) | GPT-4o-mini | Claude Haiku 4.5 |

This is configured in `backend/config.py` and transparent to the nodes — they call `get_llm(complexity="high")` or `get_llm(complexity="standard")` and the config resolves the model.

---

## README Structure

1. **One liner** — sharp, memorable
2. **Demo GIF** — the two-panel UI with claims being verified in real time
3. **Tech stack table**
4. **What it is** — 2 paragraphs: problem → how Validity works → what you get
5. **Architecture** — the agent flow diagram from this spec (Mermaid or clean ASCII)
6. **How to run** — clone → `.env` → `docker compose up` → open browser. Under 60 seconds.
7. **MCP integration** — Claude Desktop config + usage example
8. **Design decisions** — HITL rationale, source tier honesty, provider abstraction
9. **Build breakdown** — hours spent on planning / backend / frontend / MCP / debugging
10. **V2 roadmap**

---

## V2 Roadmap

- **ML source credibility classifier** — beyond domain heuristics, using features like domain authority, publication type, author signals
- **Citation verification mode** — paste text with citations, verify claims against their own cited sources
- **Batch mode** — process multiple paragraphs/documents in queue
- **Browser extension** — highlight text on any page, right-click → verify with Validity
- **Full REST API** — documented endpoints for third-party integration
- **Claim history** — store past verifications, detect when claims become outdated

---

## Build Order (Priority Sequence)

This is the order things get built. Each phase produces a working system.

### Phase 1: Core Pipeline (~8 hours)
1. FastAPI skeleton with health endpoint
2. LangGraph graph with state schema
3. Nodes 1-2: decompose + rank (LLM calls working)
4. Nodes 3-4: query generation + Serper search
5. Nodes 5-7: classify + weigh + verdict
6. Node 8: synthesize
7. End-to-end test: paste text → get verdict JSON from API

**Checkpoint:** Working backend. Paste text via curl, get structured verdict.

### Phase 2: Streaming + Frontend (~6 hours)
1. WebSocket endpoint + callback handler
2. React app scaffold (Vite)
3. InputPanel + basic submit flow
4. ThoughtPanel consuming WebSocket events
5. VerdictPanel rendering results
6. Two-panel layout, responsive

**Checkpoint:** Working web app. Paste text, watch agent work, see verdict.

### Phase 3: HITL (~3 hours)
1. LangGraph interrupt at rank node
2. WebSocket HITL event emission
3. ClaimModal component
4. Resume flow on user confirmation
5. End-to-end HITL test

**Checkpoint:** Full interactive pipeline with human-in-the-loop.

### Phase 4: MCP + Polish (~3 hours)
1. FastMCP server with `verify_text` + `verify_text_interactive`
2. Claude Desktop config + manual test
3. Docker Compose (backend + frontend)
4. `.env.example` with all options documented
5. README with architecture diagram, run instructions, MCP setup
6. Demo GIF recording

**Checkpoint:** Deployable, documented, MCP-integrated.

---

## What This Is NOT

- Not a fact-checking oracle. It retrieves evidence and presents it. The verdict is a structured summary, not ground truth.
- Not a document analysis tool. No RAG, no vector stores. Paste text in, get verification out.
- Not a research tool. It verifies specific claims, not open-ended questions.

This keeps the scope honest and the architecture clean.
