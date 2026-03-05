# Validity: Technical Specification

## Project brief

Validity is an agentic claim-verification system that decomposes text into atomic claims, retrieves adversarial web evidence for each one, tiers sources by credibility, and returns structured per-claim verdicts with full agent reasoning visible in real time. It demonstrates end-to-end agentic AI engineering: LangGraph orchestration, HITL, WebSocket streaming, MCP tool exposure, and configurable multi-provider LLM and search abstraction. The intended audience is technical interviewers and engineers evaluating modern agentic system design.

## Built with Claude Code

The entire build was executed using Claude Code. Total time was approximately 5 hours 10 minutes across planning and 5 build phases. Architectural and product decisions, including the HITL implementation strategy, the dual-model LLM pattern, and the asyncio.Event coordination approach, were made collaboratively during the session. This is an honest and notable part of the build process: the codebase was designed, written, debugged, and documented within a single Claude Code session.

## Hours breakdown

| Phase | Description | Time |
|-------|-------------|------|
| Planning | Architecture, stack decisions, product scoping | 1h 30m |
| Phase 1 | Backend pipeline, LangGraph graph, all nodes, FastAPI | 20m |
| Phase 2 | WebSocket streaming and Vite/React frontend | 20m |
| Phase 3 | HITL, LangGraph interrupt, ClaimModal wizard | 40m |
| Phase 4 | MCP server, Docker Compose, initial docs | 20m |
| Phase 5 | Iterations, prompt engineering, bug fixes, optimizations | 2h |
| **Total** | | **5h 10m** |

## Stack decisions

**LangGraph vs plain LangChain chains.** LangGraph was chosen over plain LangChain chains because the pipeline is not a linear sequence: it has conditional routing (HITL approval gating query generation), parallel execution (all search queries fired concurrently, evidence weighing run per-claim in parallel), and a named interrupt point. LangGraph's StateGraph model makes these control flows explicit and composable. A plain chain would require custom orchestration logic that LangGraph provides out of the box.

**FastAPI.** FastAPI was chosen for its native async support and first-class WebSocket handling. The pipeline is async throughout: LangGraph runs with `ainvoke()`, search queries execute with `asyncio.gather()`, and HITL coordination uses `asyncio.Event`. A synchronous framework would have required thread-pool workarounds for all of this. FastAPI's automatic OpenAPI generation also provides REST endpoint documentation at no additional cost.

**Vite and React.** Vite gives near-instant dev server startup and hot module replacement, which matters when iterating on the frontend during a timed build. React was chosen over a lighter alternative because the UI has meaningful stateful complexity: WebSocket connection lifecycle, streaming event ingestion, HITL modal state (claim approval, removal, and addition), and a two-panel layout with independent update streams. Simpler frameworks would have required manual state management that React handles naturally.

**ChromaDB (considered, removed).** ChromaDB was initially considered to cache search results and source embeddings across runs, supporting a RAG-style evidence retrieval layer. It was removed because the added complexity (embedding pipeline, vector store management, cache invalidation) was not justified for the v1 scope, where each run is independent and web search results are fetched fresh. The architecture is cleaner without it; document upload and RAG are explicitly in the V2 roadmap.

**FastMCP.** FastMCP was chosen to expose the pipeline as Claude Desktop tools because it reduces MCP server boilerplate to a decorator pattern. The `@mcp.tool` decorator handles tool registration, schema generation, and protocol compliance. The alternative (implementing the MCP protocol directly) would have added significant infrastructure code with no product benefit for this scope.

**Docker Compose.** Docker Compose provides a single-command deployment of the backend and frontend with environment variable injection via `.env`. It was chosen over bare Docker commands or a more complex orchestration layer because the deployment model is two services with a simple proxy, and Compose handles that cleanly without operational overhead.

## Build phases

**Planning.** Architecture decisions were made before any code was written: the LangGraph node sequence, the dual-model LLM strategy, the HITL approach selection (asyncio.Event vs MemorySaver), the WebSocket event schema, and the search provider abstraction interface. The state schema was defined upfront as a TypedDict to ensure all nodes shared a consistent contract. The checkpoint for this phase was a fully-specified architecture document with the exact node graph, LLM call map, and API contract.

**Phase 1: Backend pipeline.** The FastAPI skeleton, LangGraph graph, and all pipeline nodes were built: decompose, rank, query generation, web search (Serper), source classification, evidence weighing, verdict assignment, and synthesis. The graph was wired with edges and conditional routing. The checkpoint was a working backend that accepted text via a POST endpoint and returned a structured verdict JSON synchronously. All LLM calls were working against real models, and the pipeline produced correct output end-to-end.

**Phase 2: WebSocket streaming and frontend.** A WebSocket endpoint was added to FastAPI, and a custom `StreamingCallbackHandler` was built to capture node events and push them to connected clients. The React frontend was scaffolded with Vite: InputPanel for text submission, ThoughtPanel for the live event stream, and VerdictPanel for the structured results. The checkpoint was a working two-panel web app where pasting text and submitting produced a live stream of agent events followed by a rendered verdict.

**Phase 3: HITL.** The HITL node was added to the graph between rank and query generation. The node emits a `hitl_request` event over WebSocket, awaits an `asyncio.Event`, and resumes when the WebSocket handler sets it on receipt of a `hitl_response` from the client. The ClaimModal component was built in React: a step-by-step wizard for approving, removing, and adding claims before the pipeline continues. The checkpoint was an end-to-end interactive run with a visible pause, claim review, and pipeline resumption.

**Phase 4: MCP server, Docker Compose, initial docs.** The FastMCP server was built exposing three tools: `verify_text`, `verify_text_interactive`, and `get_run`. Docker Compose was configured with backend and frontend services. An `.env.example` was documented with all provider options. Initial README and SPEC were drafted. The checkpoint was a fully deployable, MCP-integrated system that could be started with `docker compose up` and used from Claude Desktop.

**Phase 5: Iterations, prompt engineering, bug fixes, optimizations.** This phase covered everything that broke under real inputs: false contradictions on numerical approximations in the weigh node, overly conservative verdict scoring in the verdict node, HITL event coordination edge cases, the reformulate node being added to handle subjective claims, and source tier classification being extended with an LLM fallback for unknown domains. See the Iterations and fixes section for detail on each.

## Architecture deep dive

### Decompose

**Purpose:** Extract every atomic statement from the input text, including both verifiable facts and subjective opinions. No filtering is applied at this stage: the decompose node's job is exhaustive extraction, not judgment.

**Inputs:** `input_text` (string)

**Outputs:** `claims` (list of dicts with id, text, claim_type, importance_score, original_text, reformulation_options)

**LLM call:** Yes, `complexity="high"`. Decomposition is the hardest call in the pipeline: the model must parse natural language, identify every assertive statement, and tag each as `verifiable` or `subjective`. A weaker model produces noisy claims that cascade errors downstream.

**Key implementation note:** The node extracts all statements up to a maximum of 8, including opinions and superlatives, and does not filter. The prompt instruction "if you are unsure whether to include something, INCLUDE IT and tag it subjective" was critical: earlier versions filtered aggressively and missed verifiable claims embedded in subjective phrasing.

---

### Reformulate

**Purpose:** For subjective claims, generate two alternative wordings that are more searchable: a cleaner version and a specific, quantifiable version. Verifiable claims pass through unchanged.

**Inputs:** `claims` (from decompose)

**Outputs:** `claims` (updated, with `reformulation_options` populated for subjective claims)

**LLM call:** Yes, `complexity="standard"`, but only for subjective claims. Verifiable claims return immediately without an LLM call.

**Key implementation note:** The node runs a single batched LLM call for all subjective claims, rather than one call per claim, to minimise latency. On failure, the node passes claims through unchanged and continues the pipeline, ensuring a failure here does not terminate a run.

---

### Rank

**Purpose:** Score every claim on verifiability (how easily it can be checked with public sources) and importance (how central it is to the text's meaning), then select the top N for verification.

**Inputs:** `claims` (from reformulate)

**Outputs:** `ranked_claims` (top N claims sorted by combined score)

**LLM call:** Yes, `complexity="standard"`. Scoring is a structured task with defined criteria and bounded output: a mid-tier model handles it reliably.

**Key implementation note:** The combined score is the average of verifiability and importance. Claims are sorted descending and truncated to `MAX_CLAIMS` (configurable, default 5). The rank node sets `ranked_claims` but does not set `approved_claims`: that is the HITL node's responsibility.

---

### HITL

**Purpose:** Pause the pipeline, emit ranked claims to the connected frontend for user review, and wait until the user approves, removes, or adds claims and confirms.

**Inputs:** `ranked_claims`

**Outputs:** `approved_claims` (the user-validated subset, potentially with custom claims added)

**LLM call:** No.

**Key implementation note:** The node operates in two modes. In interactive mode (WebSocket run), it awaits a per-run `asyncio.Event` stored on the `StreamingCallbackHandler`; the WebSocket handler sets this event when the client sends a `hitl_response` message. In skip mode (MCP call, sync endpoint, or test), no event exists and the node auto-approves all ranked claims immediately. A 5-minute timeout auto-approves if the user does not respond. Custom claims added in the modal are assigned new UUIDs and validated (empty text and claims over 500 characters are rejected).

---

### No Claims

**Purpose:** Handle the zero-approved-claims edge case without crashing the pipeline. Sets a minimal `overall_verdict` and routes to END.

**Inputs:** `approved_claims` (empty list, determined by the conditional router after HITL)

**Outputs:** `overall_verdict` (with `total_claims=0` and a descriptive summary)

**LLM call:** No.

**Key implementation note:** This node is reached via a conditional edge from HITL: if `approved_claims` is empty, the router selects `no_claims` rather than `query_gen`. This prevents all downstream nodes from receiving empty claim lists and ensures the frontend receives a well-formed `pipeline_complete` event.

---

### Query Gen

**Purpose:** For each approved claim, generate a set of adversarial search queries: affirm queries designed to find supporting evidence, and refute queries designed to find contradicting evidence.

**Inputs:** `approved_claims`

**Outputs:** `search_queries` (list of query objects with claim_id, intent, and query text)

**LLM call:** Yes, `complexity="standard"`. Generating effective refute queries requires semantic understanding of the claim to produce targeted counter-searches.

**Key implementation note:** The adversarial pair design is deliberate. It is easy to find agreement online for almost any claim. Actively searching for contradictions is what makes verification meaningful rather than confirmation search dressed as fact-checking. The prompt treats refute queries as "critical" and examples are constructed to produce genuinely adversarial queries, not just negations of the affirm queries.

---

### Search

**Purpose:** Execute all search queries concurrently against the configured search provider, tag each result with its claim_id and query intent, and deduplicate by URL within each claim.

**Inputs:** `search_queries`

**Outputs:** `search_results` (all results tagged with claim_id, query_intent, and a null source_tier placeholder)

**LLM call:** No. Uses the configured search API (Serper, Tavily, or You.com).

**Key implementation note:** All queries are fired in parallel with `asyncio.gather()`. A per-claim URL deduplication pass runs after collection to prevent the same source appearing multiple times for the same claim across different query variants. Individual query failures are caught and logged without stopping the batch.

---

### Classify

**Purpose:** Assign a credibility tier (high, mid, or low) to each search result based on its source domain.

**Inputs:** `search_results`

**Outputs:** `classified_results` (all results with `source_tier` populated)

**LLM call:** Yes, but only as a fallback. Known high-credibility domains (`.gov`, `.edu`, `arxiv.org`, peer-reviewed journals, major health agencies) and known mid-credibility domains (Reuters, BBC, AP, Wikipedia, established newspapers) are classified by heuristic with no LLM call. Only domains that fall through to the default low tier and are unknown are sent to the LLM for a second opinion.

**Key implementation note:** Classification runs concurrently for all results. Heuristic results return instantly; only unknown domains incur LLM latency. The fallback prompt asks the model to classify by domain type (government, academic, news, blog) and return a one-sentence reasoning used for the callback event detail.

---

### Weigh

**Purpose:** For each approved claim, assess every associated source: does it SUPPORT, CONTRADICT, or is it IRRELEVANT to the specific claim? Apply tier-based weights to each assessment.

**Inputs:** `classified_results`, `approved_claims`

**Outputs:** `evidence_assessments` (one assessment per source-claim pair, with weight)

**LLM call:** Yes, `complexity="high"`. Assessing whether a search snippet supports or contradicts a specific claim requires genuine comprehension: partial support, implicit contradiction, and tangential relevance are all distinct cases a weaker model conflates.

**Key implementation note:** Evidence weighing runs parallel per claim with `asyncio.gather()`. Tier weights are: high = 1.0, mid = 0.6, low = 0.3. The system prompt includes explicit rules for numerical approximations and rounding, date ranges, and partial information, added to fix a class of false contradiction bugs found during Phase 5.

---

### Verdict

**Purpose:** Assign a validity verdict (high, medium, low, or contradicted) to each claim based on its weighted evidence, using an explicit rule-based prompt.

**Inputs:** `evidence_assessments`, `approved_claims`, `classified_results`

**Outputs:** `claim_verdicts` (one verdict per claim with confidence score and split supporting/contradicting evidence lists)

**LLM call:** Yes, `complexity="standard"`. The verdict assignment uses a structured prompt with 8 explicit rules applied in priority order: tier-level contradictions trigger "contradicted" first; support counts then determine high, medium, or low.

**Key implementation note:** Verdict assignment runs parallel per claim. The prompt was rewritten in Phase 5 after discovering the original version returned "low" for claims with 8 supporting sources but no contradictions. The explicit rule "5 or more SUPPORTING sources and 0 contradicting sources = high" and "do NOT factor in source tier when determining high vs medium vs low" were added to fix this.

---

### Synthesize

**Purpose:** Aggregate all per-claim verdicts into a single overall verdict (high, medium, low, or mixed) with a 2 to 3 sentence natural language summary.

**Inputs:** `claim_verdicts`, `approved_claims`

**Outputs:** `overall_verdict` (verdict string, summary, counts by verdict type, and the full claim_verdicts list)

**LLM call:** Yes, `complexity="standard"`. The synthesis prompt accounts for claim importance scores from the rank node when weighting the overall assessment.

**Key implementation note:** A heuristic fallback is implemented for the case where the LLM call fails: if contradicted_count > 0 the overall verdict is "mixed"; if high_count is 70% or more of total it is "high"; if low_count is 50% or more it is "low"; otherwise "medium". This ensures the pipeline always produces a usable result even under LLM failure.

---

## Iterations and fixes

**Weigh node false contradictions on numerical approximations.** During Phase 5 testing with real inputs, the weigh node was flagging sources as CONTRADICTS when they cited rounded figures. A source saying "approximately 365 days" was being called a contradiction of "365.25 days". The fix was a detailed set of rules added to the system prompt: approximations within 10% are SUPPORTS, rounded date figures are SUPPORTS, and CONTRADICTS requires clear, direct disagreement. The prompt explicitly lists non-examples ("Water boils at 100 degrees" as a source for a "100°C" claim = SUPPORTS) to anchor the model's behavior on the boundary cases.

**Verdict node returning LOW for claims with 8 supporting sources.** The original verdict prompt was underspecified: it described verdicts qualitatively without numeric thresholds. Under real inputs, the model was returning "low" for claims with many supporting sources because the sources were low-tier (general .com domains). The fix was a complete prompt rewrite with an explicit 8-rule priority sequence. The key additions: source tier is irrelevant when determining high, medium, or low (it only matters for contradiction rules), and 3 or more supporting sources with 0 contradictions is "high."

**HITL asyncio.Event vs LangGraph native interrupt.** The Phase 3 HITL implementation required a choice between two approaches. LangGraph's native interrupt pattern (MemorySaver checkpointer, `GraphInterrupt` exception, `Command(resume=...)` re-invocation) would have required refactoring the Phase 2 invocation model, which used `ainvoke()` in a single async call. The `asyncio.Event` approach was chosen because it required no changes to the existing invocation pattern: the event is stored on the per-run callback handler, awaited inside the HITL node, and set by the WebSocket handler when the client responds. Both run in the same event loop. The tradeoff is that this approach does not support multi-process or distributed deployment of the pipeline, which is outside the v1 scope.

**Decompose node filtering subjective claims, attempts made, current known limitation.** The original decompose prompt instructed the model to filter out opinions, superlatives, and subjective assertions. This caused the pipeline to miss verifiable claims embedded in subjective phrasing: "This company has the most efficient supply chain in the industry" contains a verifiable competitiveness claim that was being dropped. Multiple prompt variants were tried, including a separate filter pass and confidence-weighted extraction. The final approach was to remove all filtering from decompose entirely. The node now extracts everything and tags each claim as verifiable or subjective. The reformulate node was added as a dedicated step to generate more searchable wordings for subjective claims. The remaining known limitation is that reformulation quality varies: the model sometimes produces alternatives that are not meaningfully more searchable than the original.

**Source tier classification evolution.** The initial classifier was pure domain heuristics: a fixed allowlist of high and mid domains, with everything else defaulting to low. This worked well for known sources but produced low-tier classifications for legitimate but unlisted sources. An LLM fallback was added for the unknown low-tier case: the model is given the domain name, URL, and snippet and asked to classify by source type (academic, government, news, blog). The fallback only fires for sources that did not match the heuristic lists, keeping latency low for the common case.

## What's next / V2

**Document upload and RAG.** Users occasionally want to verify claims in longer documents, not just pasted paragraphs. Document upload with a chunking and embedding pipeline was considered for v1 but deprioritised: it would have added ChromaDB, an embedding model, and a retrieval interface, tripling the infrastructure surface area. For v1, the value is in the agentic pipeline and real-time UX, not document management. This is the most natural v2 extension.

**GraphRAG.** GraphRAG (entity and relationship extraction over document corpora, with graph-based retrieval) was evaluated as a way to improve evidence coverage for claim verification. It was not included in v1 because it requires a document corpus to be meaningful, which in turn requires the document upload feature. Without that, GraphRAG adds infrastructure with no input to retrieve over.

**RAGAS eval.** RAGAS is an evaluation framework for RAG and retrieval-augmented LLM pipelines. Adding automated evaluation of verdict accuracy against ground-truth datasets would make the pipeline measurable and improvable systematically. It was deprioritised in v1 because there is no labelled ground-truth dataset for the claims being verified, and building one is a significant effort in its own right. This becomes relevant once the core pipeline is stable and iteration moves from correctness to optimisation.

**Citation verification.** A dedicated mode where users paste text that already contains citations, and the pipeline verifies each claim against its own cited source rather than performing open web search. This is a narrower, more precise verification task and was considered for v1. It was deprioritised because it requires a different retrieval path (fetch and parse specific URLs rather than open search queries) and the general web search mode demonstrates the more interesting agentic behaviour.

**Browser extension.** A browser extension would let users highlight text on any page and trigger verification in one click, removing the copy-paste step. The product value is clear. It was deprioritised in v1 because browser extension development (manifest, content script, background service worker) is a distinct engineering surface that would have dominated Phase 4 time without demonstrating anything new about the core pipeline.

**ML source credibility classifier.** The v1 domain heuristic classifier is directionally correct but coarse. An ML classifier using domain authority scores, publication type signals, author credibility, and citation counts would be more accurate, especially for the long tail of unknown domains. It was deprioritised because building a quality training dataset for source credibility is a significant data engineering effort, and the LLM fallback covers the unknown-domain case adequately for v1 purposes.

**Persistent run storage.** The current run store is in-memory: runs are lost on server restart, and the web UI and MCP server each have their own isolated store. A persistent store (Postgres, SQLite, or Redis) would enable run history, cross-session retrieval, and shared access between deployment modes. It was deprioritised in v1 because persistence adds operational complexity (database provisioning, migrations, connection pooling) that is not necessary to demonstrate the pipeline. The in-memory approach is honest and documented as a known limitation.
