# Knowledge Q&A — Complete Implementation Guide

> **Purpose:** Reference document for porting the Knowledge Q&A performance
> improvements + background-upload UX from the **HR agent** (canonical
> reference) and **Frontline agent** to a new agent (e.g. Operational
> agent).
>
> **How to use this doc:** Read Section 1 first for context. Then follow
> Section 6 (the porting checklist) end-to-end. Each checklist item points
> to the exact HR file(s) to mirror, plus notes on what's different for the
> new agent.

---

## Table of contents

1. [What problem this solved](#1-what-problem-this-solved)
2. [Architecture at a glance](#2-architecture-at-a-glance)
3. [Backend implementation](#3-backend-implementation)
4. [Frontend implementation](#4-frontend-implementation)
5. [End-to-end request flow](#5-end-to-end-request-flow)
6. [Porting checklist for a new agent](#6-porting-checklist-for-a-new-agent)
7. [Common gotchas](#7-common-gotchas)
8. [Testing checklist](#8-testing-checklist)
9. [Appendix — file map](#9-appendix--file-map)

---

## 1. What problem this solved

### Before

- Uploading a 200-page PDF took **2-4 minutes**. The upload dialog blocked
  the entire UI. Users had to sit and wait, or navigate away and lose
  progress.
- Asking a question about that PDF took **130-230 seconds** per query,
  every query. Nothing was cached.
- Answers often started with boilerplate ("Based on the provided document
  snippets…") and dumped verbatim chunks.
- Table-of-contents pages, cover pages, and index pages polluted retrieval —
  a question about "Dark Prompt" would return TOC lines like
  `5.8 WebPlatform: DarkPrompt . . . . . 58` with no substantive content,
  and the LLM correctly refused to answer.
- No way to diagnose what was slow.

### After

- Uploads are **fully non-blocking**. Dialog closes immediately. A floating
  pill in the bottom-right shows progress. User can navigate anywhere,
  upload more files, run Q&A queries. Toast on start + toast on completion.
- Q&A responses drop from **160s to 3-10s** on first query, **sub-second**
  on repeat (via answer cache).
- Every response shows a **timing breakdown** in the chat badge so any
  regression is instantly visible.
- Live-ticking clock while the model is thinking.
- Answers are concise and grounded — no preamble, no verbatim quotes.

### The key wins in one table

| Fix | Latency saved |
|-----|--------------|
| FAISS index (replaces O(N) Python cosine) | ~170s for a 1000-chunk corpus |
| MSSQL `.only()` on top-K fetch | 170s → 1.3s (chained-queryset plan-cache bug) |
| Answer cache | Repeat questions: 3-10s → <100ms |
| Tighter prompt + smaller excerpts | 15-30% off final LLM call |
| Query embedding cache | 500ms per query saved on repeat |
| TOC/junk chunk filter | Better answers — retrieval doesn't waste slots on dot-leader lines |
| Background upload manager | UI never blocks — huge UX win |

---

## 2. Architecture at a glance

Every Knowledge Q&A agent has the **same 4-layer shape**:

```
User asks question
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│  API view (api/views/*.py)                                       │
│    - Receives HTTP POST                                          │
│    - Calls Agent.answer_question(...)                            │
│    - Returns response dict as JSON                               │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│  Agent (core/<Agent>_agent/<agent>_agent.py)                     │
│    - Answer cache lookup                                         │
│    - Delegates retrieval to KnowledgeService                     │
│    - Composes prompt + calls _call_llm                           │
│    - Stamps timing_ms on response                                │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│  KnowledgeService (core/<Agent>_agent/services.py)               │
│    - Hybrid retrieval: FAISS semantic + SQL keyword + RRF        │
│    - Skips junk chunks                                           │
│    - Records per-phase timing on self.last_retrieval_timing      │
└──────────────────────────────────────────────────────────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│  Storage layer                                                   │
│    - FAISS index on disk (<agent>_vector_indexes/company_N.faiss)│
│    - DocumentChunk rows in MSSQL (embedding as JSON string)      │
└──────────────────────────────────────────────────────────────────┘
```

And the **document lifecycle**:

```
User uploads document
      │
      ▼  (XHR with onProgress → BackgroundUploadManager)
Upload endpoint (multipart POST)
      │
      ▼  (returns 202 with document_id + processing_status='pending')
Celery task: process_document
    - Extract text from PDF
    - Chunk (with TOC filter)
    - Batch-embed chunks
    - Save DocumentChunk rows
    - mark_index_dirty(company_id)      ← invalidates FAISS
    - invalidate_answer_cache_for_company()  ← clears answer cache
      │
      ▼
Client polls /status endpoint every 1.5s
      │
      ▼
When processing_status == 'ready':
    - Toast "Indexing complete"
    - Next query rebuilds FAISS from the new chunks
```

---

## 3. Backend implementation

### 3.1 Chunking with TOC/junk filter

**File pattern:** `<agent>_agent/chunking.py`

The chunker rejects table-of-contents, index, and cover-page fragments
before they're stored. These match keywords densely (bad for retrieval) but
carry no explanation.

**HR reference:** [hr_agent/chunking.py](hr_agent/chunking.py). See
`_looks_like_toc_or_index`.

**Frontline reference:** [Frontline_agent/chunking.py](Frontline_agent/chunking.py). See
`looks_like_toc_or_index` (public, no underscore).

**Three heuristics (all three files use the same regexes):**

```python
_DOT_LEADER_RE = re.compile(r'\.{3,}|(?:\.\s){3,}')
_PAGE_NUM_ONLY_RE = re.compile(r'^\s*(?:page\s*)?\d{1,4}\s*$', re.IGNORECASE)
_WORD_RE = re.compile(r'[A-Za-z]{2,}')


def looks_like_toc_or_index(text: str) -> bool:
    if not text:
        return True
    stripped = text.strip()
    if not stripped:
        return True

    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if not lines:
        return True

    # 1. Line-ratio heuristic
    dot_leader_lines = sum(1 for ln in lines if _DOT_LEADER_RE.search(ln))
    page_num_lines = sum(1 for ln in lines if _PAGE_NUM_ONLY_RE.match(ln))
    junk_ratio = (dot_leader_lines + page_num_lines) / max(len(lines), 1)
    if junk_ratio >= 0.5 and len(lines) >= 3:
        return True

    # 2. Letter-count heuristic
    letters = sum(len(m.group(0)) for m in _WORD_RE.finditer(stripped))
    if letters < 40:
        return True

    return False
```

**Where to call it:** inside the chunking loop in the Celery processing
task, before appending to the chunks list. See
[hr_agent/tasks.py:174-186](hr_agent/tasks.py#L174-L186) for the section-aware
branch and [hr_agent/tasks.py:190-197](hr_agent/tasks.py#L190-L197) for the naive
fallback branch.

### 3.2 Per-company FAISS vector store

**File pattern:** `<agent>_agent/vector_store.py`

**HR reference:** [hr_agent/vector_store.py](hr_agent/vector_store.py)

**Frontline reference:** [Frontline_agent/vector_store.py](Frontline_agent/vector_store.py)

**Design:** One FAISS `IndexFlatIP` (inner product on L2-normalized
vectors = cosine similarity) **per company**, persisted to disk as
`MEDIA_ROOT/<agent>_vector_indexes/company_<id>.faiss`. Meta sidecar JSON
stores the `row → chunk_id` mapping.

**Public API (identical between HR and Frontline):**

```python
def get_store(company_id: int) -> Optional[Store]:
    """Return a ready-to-search store or None (no FAISS / no chunks yet)."""

def mark_index_dirty(company_id: int) -> None:
    """Signal that the index needs a rebuild on next query."""

def evict(company_id: int) -> None:
    """Drop the in-process cache entry (used by tests)."""
```

**Rebuild triggers:** the Celery task calls `mark_index_dirty(company_id)`
after each successful embed. Next query loads the index; if dirty, it's
rebuilt from scratch. Incremental upserts aren't worth the complexity —
rebuilding from scratch takes seconds and Celery does it in a worker.

**Startup guard:** at import time, log whether FAISS is active or not.
Optionally raise if `<AGENT>_REQUIRE_FAISS=True` in settings, so a broken
deploy doesn't silently serve slow queries.

**Copy-paste starting point** (adapt the model imports for the new agent):

Whole file from HR is ~280 lines. Copy it, rename:

- `HRFaissVectorStore` → `<Agent>FaissVectorStore`
- `hr_vector_indexes/` → `<agent>_vector_indexes/`
- `from hr_agent.models import HRDocumentChunk` → your agent's chunk model
- `filter(document__company_id=...)` → verify your chunk model has the same
  `document.company_id` relation
- `HR_REQUIRE_FAISS` → `<AGENT>_REQUIRE_FAISS`

### 3.3 Retrieval service — the heart of the fix

**File pattern:** `core/<Agent>_agent/services.py`

**HR reference:** [core/HR_agent/services.py](core/HR_agent/services.py). Class `HRKnowledgeService`.

This file has three critical parts:

#### 3.3.1 Module-level caches

All three caches are `dict` + `threading.Lock` bounded at 20,000 entries
(chunk embeddings) or 512 (query embeddings). Half-drop eviction when full.

- `_CHUNK_EMBEDDING_CACHE` — `chunk_id → numpy array` (parsed once, reused
  forever)
- `_QUERY_EMBEDDING_CACHE` — `sha256(query) → numpy array` (repeat queries
  skip the embedding API entirely)
- `_CHUNK_JUNK_CACHE` — `chunk_id → bool` (junk classification cached so
  the regex only runs once per chunk)

See [core/HR_agent/services.py:24-135](core/HR_agent/services.py#L24-L135)
for the exact implementation.

**Why these matter:** on a cold cache the JSON-scan path costs 200ms per
chunk. With the cache warm, cosine is a numpy `np.dot` — sub-microsecond.
The query cache means asking "how many PTO days?" a second time skips the
OpenAI embedding call entirely (~500ms saved).

#### 3.3.2 The `search_knowledge` method — hybrid retrieval

The retrieval flow, in order:

```python
def search_knowledge(self, query, ...):
    self.last_retrieval_timing = {}         # for per-phase timing
    self.last_retrieval_path = ''           # human-readable path marker

    # 1. Fetch allowed doc IDs (visibility + confidentiality filters)
    doc_ids = list(docs.values_list('id', flat=True))

    # 2. Build a base chunks_qs (with .only for column pruning)
    chunks_qs = HRDocumentChunk.objects.filter(document_id__in=doc_ids).only(...)

    # 3. Semantic search
    if self.embedding_service.is_available():
        qvec = _cache_get_query_vec(query, self.embedding_service)
        if qvec is not None:
            # 3a. Try FAISS first — O(log N)
            try:
                from <agent>_agent import vector_store as _vs
                if _vs.FAISS_AVAILABLE:
                    store = _vs.get_store(self.company_id)
                    if store is not None:
                        candidate_ids = set(chunks_qs.values_list('id', flat=True))
                        hits = store.search(qvec, k=50, candidate_chunk_ids=candidate_ids)
                        if hits:
                            used_faiss = True
                            semantic_hits = [(cid, float(score)) for cid, score in hits]
            except Exception: ...

            # 3b. Fallback to Python scan (only when FAISS didn't return hits)
            if not used_faiss:
                for c in chunks_qs.iterator(chunk_size=500):
                    if _is_junk_chunk(c.id, c.chunk_text): continue
                    cvec = _cache_get_chunk_vec(c.id, c.embedding)
                    score = _semantic_score(qvec, cvec)
                    semantic_hits.append((c.id, score))

    # 4. Keyword search (SQL icontains)
    keyword_hits = list(chunks_qs.filter(chunk_text__icontains=query[:80]).values_list('id', flat=True)[:50])

    # 5. RRF merge
    rrf = { chunk_id: sum(1 / (k + rank + 1) for each hit) }
    ordered = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)[:max_results * 2]

    # 6. Fresh queryset + .only() for top-K metadata (CRITICAL MSSQL fix)
    chunk_map = {c.id: c for c in HRDocumentChunk.objects
                 .filter(id__in=top_ids)
                 .select_related('document')
                 .only('id', 'document_id', 'chunk_text', 'chunk_index',
                       'section_heading', 'page_number', 'document__title')}

    # 7. Build output, defensively skipping junk again
    return [...][:max_results]
```

**Critical detail — the MSSQL `.only()` fix:** chaining `.filter()` on top
of a queryset with `select_related` triggered a pathological query plan on
MSSQL — 174 seconds for 50 rows. Always use a **fresh queryset from
`Model.objects`** for the top-K fetch, with an explicit `.only(...)`
column list. See [core/HR_agent/services.py:317-326](core/HR_agent/services.py#L317-L326).

#### 3.3.3 Per-phase timing

Every phase writes to `self.last_retrieval_timing` and appends to
`self.last_retrieval_path`. This gets bubbled up to the response so the
frontend badge can render `path: faiss(store_ready=1ms)|hits=50|kept=50…`
and `query_embed=0.7s · faiss_search=<50ms · chunk_fetch=0.5s`.

Timing keys used:
- `doc_filter` — the doc-ID SELECT
- `query_embed` — cache lookup + (on miss) API call for query embedding
- `faiss_candidates` — chunk-ID set-building for the FAISS filter
- `faiss_search` — the FAISS `.search()` call itself
- `chunk_fetch` — the top-K metadata fetch (the one we `.only()`'d)
- `output_build` — the loop that constructs result dicts
- `json_scan` — populated only when the Python fallback ran
- `json_scan_chunks` — how many chunks the fallback processed
- `keyword` — SQL icontains
- `rerank` — LLM re-rank (Frontline only; HR doesn't do this)
- `search_total` — wall-clock total for the whole call

### 3.4 Agent entry — answer cache + timing bubbling

**File pattern:** `core/<Agent>_agent/<agent>_agent.py`

**HR reference:** [core/HR_agent/hr_agent.py](core/HR_agent/hr_agent.py)

Three things live here:

#### 3.4.1 In-process answer cache

Module-level `dict` keyed by
`sha256({company_id, scope_or_role, question.lower().strip()})`. TTL default
5 minutes, tunable via `<AGENT>_ANSWER_CACHE_TTL_SECONDS`. Bounded at
2000 entries, half-drop eviction when full.

**Skip caching when the answer is personalised** (e.g. HR skips caching
when `asker_employee` is set to avoid cross-employee leaks of leave-balance
answers). Adapt this rule for your agent.

Helpers exposed from the module:
- `_answer_cache_key(...)` — deterministic key builder
- `_answer_cache_get(key, ttl)` — TTL-aware lookup
- `_answer_cache_put(key, resp)` — store with bounded eviction
- `invalidate_answer_cache_for_company(company_id)` — called from the
  processing task when a new doc goes live

#### 3.4.2 `answer_question` flow

```python
def answer_question(self, question, ...):
    _t_overall = time.time()
    timing_ms = {}

    # 1. Cache check
    if cache_ttl > 0 and (no personalisation):
        cache_key = _answer_cache_key(...)
        cached = _answer_cache_get(cache_key, cache_ttl)
        if cached is not None:
            return {**cached, 'cache_hit': True, 'timing_ms': {'total': ..., 'cache': True}}

    # 2. Retrieval (timed)
    _t_retr = time.time()
    knowledge_result = self.knowledge_service.get_answer(question, ...)
    timing_ms['retrieval'] = int((time.time() - _t_retr) * 1000)
    timing_ms['retrieval_breakdown'] = dict(self.knowledge_service.last_retrieval_timing)
    timing_ms['retrieval_path'] = self.knowledge_service.last_retrieval_path

    # 3. Handle 'no verified info' case (still returns timing_ms)
    if not knowledge_result.get('has_verified_info'):
        return {..., 'timing_ms': timing_ms}

    # 4. LLM call (timed)
    _t_llm = time.time()
    formatted = self._call_llm(
        prompt=get_knowledge_prompt(...),
        system_prompt=self.system_prompt,
        temperature=0.3,
        max_tokens=int(getattr(settings, '<AGENT>_QA_MAX_TOKENS', 300)),
    )
    timing_ms['llm'] = int((time.time() - _t_llm) * 1000)
    timing_ms['total'] = int((time.time() - _t_overall) * 1000)

    # 5. Cache + return
    response = {..., 'timing_ms': timing_ms}
    _answer_cache_put(cache_key, response)
    return response
```

#### 3.4.3 LLM tuning knobs

Tunable via Django settings:

- `<AGENT>_QA_MAX_TOKENS` — cap on final answer length. HR: 400 (policy
  detail needs room). Frontline: 250 (support answers are short). Operational:
  pick based on your typical answer length.
- `<AGENT>_ANSWER_CACHE_TTL_SECONDS` — cache TTL, default 300 (5 min).
- `<AGENT>_RAG_MIN_CONFIDENCE` — semantic score below this = "no verified
  info". Default 0.3.
- (Frontline only) `FRONTLINE_RERANK_SKIP_SCORE` — skip LLM re-rank when
  top semantic hit is already this confident. Default 0.55.
- (Frontline only) `FRONTLINE_REQUIRE_FAISS` — fail loud at startup if
  FAISS isn't installed. Off by default.

### 3.5 Prompts

**File pattern:** `core/<Agent>_agent/prompts.py`

**HR reference:** [core/HR_agent/prompts.py](core/HR_agent/prompts.py)

Two things matter here:

#### 3.5.1 The "no preamble" instruction block

The knowledge prompt MUST explicitly ban:
- "Based on the provided document snippets…"
- "According to the excerpts…"
- Verbatim block-quotes of chunk content
- Meta-commentary before answering

Otherwise the LLM will pad every answer with 30-50 tokens of boilerplate,
which slows streaming AND makes answers wordy. See
[core/HR_agent/prompts.py:51-61](core/HR_agent/prompts.py#L51-L61) for the
exact rule block.

#### 3.5.2 Per-excerpt cap

Cap each retrieved chunk's body at **1500 characters** in
`get_knowledge_prompt`. See
[core/HR_agent/prompts.py:87-93](core/HR_agent/prompts.py#L87-L93).

Frontline uses two caps because it has a monolithic-document fallback path:
[core/Frontline_agent/prompts.py:154-171](core/Frontline_agent/prompts.py#L154-L171).

**Why this matters:** prompt size is the single biggest lever on
time-to-first-token. A 15,000-char prompt takes 3-8s to receive the first
token from OpenAI; a 3,000-char prompt takes 0.5-1s.

### 3.6 Document processing task — cache invalidation

**File pattern:** `<agent>_agent/tasks.py::process_<agent>_document`

**HR reference:** [hr_agent/tasks.py:220-243](hr_agent/tasks.py#L220-L243)

After the doc's `processing_status` flips to `'ready'`, do these two
things:

```python
# 1. Invalidate FAISS index for this company
try:
    if has_embeddings and document.company_id:
        from <agent>_agent.vector_store import mark_index_dirty
        mark_index_dirty(document.company_id)
except Exception:
    logger.exception("failed to mark FAISS index dirty")

# 2. Invalidate answer cache for this company
try:
    if document.company_id:
        from core.<Agent>_agent.<agent>_agent import invalidate_answer_cache_for_company
        invalidate_answer_cache_for_company(document.company_id)
except Exception:
    logger.exception("failed to invalidate answer cache")
```

Both are wrapped in try/except because a cache invalidation failure must
never break a successful upload.

### 3.7 API endpoints

**HR reference file:** [api/views/hr_agent.py](api/views/hr_agent.py)

Three endpoints matter for Q&A + upload UX:

#### 3.7.1 Q&A endpoint

```
POST /api/hr/knowledge-qa
Body: { question, chat_history? }
Returns: { status: 'success', data: { answer, has_verified_info,
           citations, timing_ms, cache_hit, ... } }
```

See [api/views/hr_agent.py::hr_knowledge_qa](api/views/hr_agent.py). Just
delegates to `HRAgent.answer_question(...)` and returns the result.

#### 3.7.2 Upload endpoint

```
POST /api/hr/documents/upload
Multipart: file, title, description, document_type, confidentiality, ...
Returns: 202 { status: 'accepted', data: { id, processing_status,
           dispatch_mode: 'celery'|'inline' } }
```

Kicks off `process_hr_document.delay(document.id)` (Celery) and returns
immediately. If Celery isn't reachable, falls back to `.apply()` (inline)
so uploads still work in dev.

#### 3.7.3 Status endpoint (lightweight, no access-log)

```
GET /api/hr/documents/<id>/status
Returns: { status: 'success', data: {
    id, processing_status, chunks_processed, chunks_total,
    percent, processing_error, is_indexed, updated_at
}}
```

**Critical:** this endpoint MUST skip the normal `HRDocumentAccessLog`
write. Frontend polls this every 1.5s during indexing — if it wrote an
access-log row per poll, a single 3-minute indexing would spam 120 rows
into the audit trail.

See [api/views/hr_agent.py::get_hr_document_status](api/views/hr_agent.py).

**Note:** Frontline's status endpoint returns `progress_percent` while HR
returns `percent`. The frontend handles both — see
`s.percent != null ? s.percent : (s.progress_percent != null ? s.progress_percent : 0)`
in [PaPerProjectFront/src/components/shared/BackgroundUploadManager.jsx](PaPerProjectFront/src/components/shared/BackgroundUploadManager.jsx).
Pick either shape for the new agent, but be consistent.

### 3.8 Management command — reindex existing docs

**HR reference:** [hr_agent/management/commands/reindex_hr_documents.py](hr_agent/management/commands/reindex_hr_documents.py)

Usage:

```bash
python manage.py reindex_hr_documents                # all docs, all companies
python manage.py reindex_hr_documents --company 3    # one company
python manage.py reindex_hr_documents --doc 42       # one doc
python manage.py reindex_hr_documents --failed       # only failed
python manage.py reindex_hr_documents --async        # dispatch via Celery
```

Two purposes:
1. **Purge pre-fix junk** — docs indexed before the TOC filter existed
   still have dot-leader chunks. This command re-runs the chunker with the
   filter active.
2. **Rebuild FAISS** — marks the FAISS index dirty for all affected
   companies so retrieval rebuilds from the fresh chunks.

---

## 4. Frontend implementation

### 4.1 Service layer — XHR upload + status polling

**File pattern:** `PaPerProjectFront/src/services/<agent>AgentService.js`

**HR reference:** [PaPerProjectFront/src/services/hrAgentService.js](PaPerProjectFront/src/services/hrAgentService.js)

Two functions matter:

#### 4.1.1 `uploadHRDocument` (XHR-based with progress)

Uses `XMLHttpRequest` (not `fetch`) because fetch still can't report
upload-side progress in a portable way. Exposes `options.onProgress(
{ loaded, total, percent })` and `options.signal` (AbortSignal) for
cancellation.

Copy-paste starting point from
[hrAgentService.js:113-186](PaPerProjectFront/src/services/hrAgentService.js#L113-L186).
Change endpoint URL + auth token key for your agent.

#### 4.1.2 `getHRDocumentStatus` (thin GET wrapper)

Just calls the status endpoint. Used by the BackgroundUploadManager's
polling loop.

### 4.2 BackgroundUploadManager — global non-blocking upload UX

**File:** [PaPerProjectFront/src/components/shared/BackgroundUploadManager.jsx](PaPerProjectFront/src/components/shared/BackgroundUploadManager.jsx)

**This is shared across all agents** — HR, Frontline, and the new
Operational agent all plug into the same manager. Do NOT create a separate
one per agent.

**How it works:**

1. Provider is mounted **once** at the root of the app
   ([App.jsx:280-282](PaPerProjectFront/src/App.jsx#L280-L282)).
2. It owns a Map-like state: `{ upload_id → { title, agent, status,
   uploadPercent, indexPercent, ... } }`.
3. Renders a floating pill in the bottom-right corner via `createPortal`
   to `document.body`.
4. Pill is hidden when there are no active uploads.
5. Any component can call `useBackgroundUpload().startUpload(...)`:

```jsx
const { startUpload } = useBackgroundUpload();

startUpload({
  title: file.name,
  agent: 'operational',              // ← agent name for the colored badge
  upload: (onProgress) => yourAgentService.uploadDocument(file, ..., { onProgress }),
  poll: (documentId) => yourAgentService.getDocumentStatus(documentId),
  onDone: (result) => refreshYourDocsList(),
});
```

**What happens next (owned by the manager, not the caller):**

1. Immediate toast "Upload started".
2. XHR upload runs; progress streamed into the pill.
3. When upload completes, manager polls `/status` every 1.5s until
   `ready`/`failed` or 15-minute timeout.
4. Toast fires on completion (or failure).
5. Auto-dismisses the pill entry 8s after completion.

**The caller UI can close its dialog immediately** — the upload survives
route changes because the provider sits above `<Routes>`.

**No changes needed for a new agent** — just call `startUpload` with the
right agent name and the right service callables.

### 4.3 ElapsedTimer — live "thinking" clock

**File:** [PaPerProjectFront/src/components/frontline/chatShellUtils.jsx](PaPerProjectFront/src/components/frontline/chatShellUtils.jsx) (search for `ElapsedTimer`)

Self-updating counter. Renders "3.4s" and ticks every 100ms. Owns its own
`setInterval`.

Usage (in the "thinking…" spinner block):

```jsx
{loading && (
  <div className="flex items-center gap-2">
    <Loader2 className="animate-spin" />
    <span>Thinking…</span>
    <span className="text-xs font-mono">
      <ElapsedTimer since={loadingStartedAt} />
    </span>
  </div>
)}
```

State plumbing:

```jsx
const [loading, setLoading] = useState(false);
const [loadingStartedAt, setLoadingStartedAt] = useState(null);

const handleSubmit = async () => {
  setLoading(true);
  const startedAt = performance.now();
  setLoadingStartedAt(startedAt);
  try {
    const res = await service.askQuestion(q);
    ...
  } finally {
    setLoading(false);
    setLoadingStartedAt(null);
  }
};
```

### 4.4 Response-time badge with timing breakdown

Rendered under each assistant message. Shows:

- Total response time (`⏱ Answered in 3.47s`)
- Breakdown when total > 1s (`retrieval 1.1s · llm 2.1s`)
- Sub-phase breakdown when retrieval > 1s (`faiss_search=<50ms · chunk_fetch=0.5s`)
- Server-side retrieval path marker (`path: faiss(store_ready=1ms)|hits=50|`)
- Green "cached" pill when it was an answer-cache hit

**HR reference:** [HRKnowledgeQAAgent.jsx:543-587](PaPerProjectFront/src/components/hr/HRKnowledgeQAAgent.jsx#L543-L587)

**Critical persistence detail:** the timing must be nested inside
`responseData` (not top-level on the message object) because the backend's
`_normalize_chat` only preserves `role`, `content`, and `responseData`
when the chat is re-fetched. Top-level fields on `msg` get stripped on
re-render.

Render with the fallback pattern:

```jsx
const t = msg.responseData?.responseTimeMs ?? msg.responseTimeMs;
```

That way freshly-sent messages (top-level) AND re-fetched messages
(inside `responseData`) both render correctly.

### 4.5 Dashboard integration

Two-line change to enqueue uploads via the manager. See the HR pattern at
[HRDashboard.jsx:449-478](PaPerProjectFront/src/components/hr/HRDashboard.jsx#L449-L478).

```jsx
import { useBackgroundUpload } from '@/components/shared/BackgroundUploadManager';

function YourDashboard() {
  const { startUpload: startBackgroundUpload } = useBackgroundUpload();

  const handleUpload = () => {
    if (!uploadFile) return;
    const file = uploadFile;
    const title = uploadTitle || file.name;

    startBackgroundUpload({
      title,
      agent: 'operational',
      upload: (onProgress) => yourAgentService.uploadDocument(file, title, ..., { onProgress }),
      poll: (documentId) => yourAgentService.getDocumentStatus(documentId),
      onDone: () => loadDocuments(),
    });

    // Close the dialog IMMEDIATELY — the pill takes over from here.
    setUploadOpen(false);
    setUploadFile(null);
    setUploadTitle('');
  };
}
```

No local progress state, no polling loop, no "uploading" flag. The manager
owns it all.

---

## 5. End-to-end request flow

### 5.1 First upload of a large doc

```
0.0s  User picks file, clicks Upload
0.0s  Dialog closes; toast "Upload started"; bottom-right pill appears (violet, spinning)
0.0-45s  XHR uploads the file; pill shows violet bar 0→100%
45s   Upload completes; server returns 202 with document_id
45s   Celery task begins: extract → chunk → embed
45-90s  Client polls /status every 1.5s; pill switches to amber "Indexing 42/187 chunks"
90s   Server marks processing_status='ready', calls mark_index_dirty(company_id) + invalidate_answer_cache
90s   Client sees 'ready', fires toast "Indexing complete", pill turns green
98s   Pill auto-dismisses
```

### 5.2 First Q&A query on the new doc (cold)

```
0.0s  User types question, hits Enter
0.0s  Chat shows "Thinking… 0.0s"
0.7s  Query embedding: cached? No → OpenAI API call (~500ms), stored in cache
0.7s  FAISS: get_store(company_id) → cache miss → build index from DB (~3s for 1000 chunks)
3.7s  FAISS search: <50ms, returns 50 hits
3.7s  chunk_fetch: fresh queryset + .only(), 50 rows from MSSQL (~500ms)
4.2s  RRF merge + junk filter
4.2s  Prompt composition (top-3 excerpts, 800 chars each)
4.2s  LLM call: ~2.5s
6.7s  Response returns with timing_ms
6.7s  Badge shows: ⏱ Answered in 6.70s (retrieval 4.2s · llm 2.5s)
       path: faiss(store_ready=3000ms)|hits=50|kept=50…|
```

### 5.3 Second Q&A query (warm)

```
0.0s  User types question, hits Enter
0.0s  Cache lookup by (company, scope, question.strip().lower())
      MISS (different question)
0.1s  Query embedding: cache miss → OpenAI API (~500ms)
0.6s  FAISS: store is cached in-process → 0ms
0.6s  FAISS search: <50ms
0.7s  chunk_fetch: 500ms
1.2s  LLM call: 2.5s
3.7s  Response
3.7s  Badge: ⏱ Answered in 3.70s (retrieval 1.2s · llm 2.5s)
```

### 5.4 Third Q&A query (same question)

```
0.0s  Cache lookup — HIT
0.1s  Response
0.1s  Badge: ⏱ Answered in 0.10s [cached]
```

### 5.5 After a new doc upload → next query is cold again

```
Upload completes → mark_index_dirty + invalidate_answer_cache
Next query:
  - Answer cache: MISS (cleared)
  - FAISS: needs rebuild (dirty flag) → rebuild from DB
  - LLM
  → 5-10s

Query after that: back to warm-cache speeds (3-4s)
```

---

## 6. Porting checklist for a new agent

Follow this in order. Every checkbox maps to a specific file to create or
modify. Use the HR agent as your canonical reference.

### Backend

- [ ] **Create `<agent>_agent/chunking.py`** with `looks_like_toc_or_index`.
  Mirror [hr_agent/chunking.py](hr_agent/chunking.py) exactly. Rename the
  helper if you prefer a different visibility (public vs `_underscore`).
- [ ] **Wire the TOC filter into the chunking loop** in
  `<agent>_agent/tasks.py::process_<agent>_document`. Skip appending
  chunks where `looks_like_toc_or_index(clean_chunk)` is True. See
  [hr_agent/tasks.py:174-197](hr_agent/tasks.py#L174-L197).
- [ ] **Create `<agent>_agent/vector_store.py`**. Copy
  [hr_agent/vector_store.py](hr_agent/vector_store.py) whole; replace
  `HRDocumentChunk` with your chunk model, `hr_vector_indexes` with
  `<agent>_vector_indexes`, and `HR_REQUIRE_FAISS` with your setting name.
- [ ] **Add caches + junk-check helpers to `core/<Agent>_agent/services.py`**.
  Mirror the module-level block at
  [core/HR_agent/services.py:24-135](core/HR_agent/services.py#L24-L135). If
  your agent's junk detector is named differently, adjust the import in
  `_is_junk_chunk`.
- [ ] **Rewrite `search_knowledge` (or equivalent) with the hybrid FAISS +
  keyword + RRF flow.** Mirror
  [core/HR_agent/services.py:225-407](core/HR_agent/services.py#L225-L407).
  Adapt the confidentiality/visibility filters for your agent's data model.
- [ ] **CRITICAL: use a fresh queryset with `.only()` for the top-K fetch.**
  Do NOT chain `.filter()` on an already-`select_related`'d queryset. See
  [core/HR_agent/services.py:378-390](core/HR_agent/services.py#L378-L390).
- [ ] **Add per-phase timing.** Every phase writes to
  `self.last_retrieval_timing`. See
  [core/HR_agent/services.py:175-176](core/HR_agent/services.py#L175-L176)
  for setup and the various `_t = time.time()` blocks throughout.
- [ ] **Add answer cache to `core/<Agent>_agent/<agent>_agent.py`**.
  Mirror [core/HR_agent/hr_agent.py:22-75](core/HR_agent/hr_agent.py#L22-L75).
  Adjust the cache key to include whatever "scope" fields matter for your
  agent (project ID, department ID, whatever).
- [ ] **Wrap `answer_question` with cache check + timing.** Mirror
  [core/HR_agent/hr_agent.py:90-172](core/HR_agent/hr_agent.py#L90-L172).
- [ ] **Tune LLM knobs.** Set `<AGENT>_QA_MAX_TOKENS` default appropriate
  for your agent (short answers = 250, long = 400+). Reduce `max_results`
  default to 3 unless you need more.
- [ ] **Update prompts.** Copy the seven-rule block from
  [core/HR_agent/prompts.py:51-61](core/HR_agent/prompts.py#L51-L61) into
  your agent's knowledge prompt. Cap per-excerpt at 1500 chars.
- [ ] **Add FAISS invalidation + answer cache invalidation** at the end
  of your processing task. See
  [hr_agent/tasks.py:226-241](hr_agent/tasks.py#L226-L241).
- [ ] **Add a lightweight status endpoint** at
  `/api/<agent>/documents/<id>/status`. Return `processing_status`,
  `chunks_processed`, `chunks_total`, `percent`, `processing_error`.
  Do NOT write to the access log. See
  [api/views/hr_agent.py::get_hr_document_status](api/views/hr_agent.py).
- [ ] **Add a management command**
  `<agent>_agent/management/commands/reindex_<agent>_documents.py`.
  Copy [hr_agent/management/commands/reindex_hr_documents.py](hr_agent/management/commands/reindex_hr_documents.py)
  and adjust imports.

### Frontend

- [ ] **Update the service layer.** In
  `PaPerProjectFront/src/services/<agent>AgentService.js`, mirror the
  XHR-based `uploadHRDocument` and the thin `getHRDocumentStatus` wrapper
  from
  [hrAgentService.js:113-201](PaPerProjectFront/src/services/hrAgentService.js#L113-L201).
- [ ] **Wire the dashboard upload to use the BackgroundUploadManager.**
  Do NOT create a new manager — reuse the shared one. See
  [HRDashboard.jsx:24](PaPerProjectFront/src/components/hr/HRDashboard.jsx#L24)
  (import), [HRDashboard.jsx:91](PaPerProjectFront/src/components/hr/HRDashboard.jsx#L91)
  (hook), and
  [HRDashboard.jsx:449-478](PaPerProjectFront/src/components/hr/HRDashboard.jsx#L449-L478)
  (handler).
- [ ] **Remove the local upload progress state and inline progress bars
  from your dialog.** The pill takes over. See what was deleted from HR at
  the same commit.
- [ ] **Add the ElapsedTimer + timing badge to your Q&A chat.** Import
  `ElapsedTimer` from `chatShellUtils.jsx` (see
  [HRKnowledgeQAAgent.jsx:28](PaPerProjectFront/src/components/hr/HRKnowledgeQAAgent.jsx#L28)),
  add `loadingStartedAt` state, render it inside the thinking spinner.
  Render the timing badge under each assistant message (see
  [HRKnowledgeQAAgent.jsx:543-587](PaPerProjectFront/src/components/hr/HRKnowledgeQAAgent.jsx#L543-L587)).
- [ ] **Nest `responseTimeMs` and `timing_ms` inside `responseData`** so
  they survive backend round-trips. Read with fallback:
  `msg.responseData?.responseTimeMs ?? msg.responseTimeMs`.
- [ ] **If you have a floating chat too:** same treatment — inline
  progress card during upload, ElapsedTimer during thinking, timing badge
  on assistant messages. See
  [HRFloatingChat.jsx](PaPerProjectFront/src/components/hr/HRFloatingChat.jsx)
  for the whole pattern.

### One-time cleanup

- [ ] Run `python manage.py reindex_<agent>_documents --company <id>` for
  each existing tenant to purge pre-fix TOC junk from the DB and rebuild
  the FAISS index with the new pipeline.

---

## 7. Common gotchas

### 7.1 FAISS "installed" but Django doesn't see it

`pip install faiss-cpu` into the wrong Python venv. Symptoms:
`json_scan=...` shows up in the timing breakdown even after installing.

Fix: verify with
`python -c "import faiss; print(faiss.__version__)"` inside the exact
Python your Django runs under. If it fails, `pip install faiss-cpu` from
that Python.

Set `FRONTLINE_REQUIRE_FAISS=True` (or the equivalent for your agent) in
prod settings to fail loud instead of silently serving slow queries.

### 7.2 MSSQL 170-second query on the top-K fetch

Cause: chaining `.filter()` on a queryset with `select_related` triggers a
pathological plan-cache path.

Fix: always use a **fresh queryset from `Model.objects`** for the top-K
fetch, with explicit `.only(...)` column list. See §3.3.2 above.

### 7.3 Answer cache serves stale content

Cause: cache invalidation not wired into the processing task.

Fix: at the end of `process_<agent>_document` (after `processing_status='ready'`),
call `invalidate_answer_cache_for_company(document.company_id)`. Wrap in
try/except so a cache failure doesn't break the upload.

### 7.4 Response-time badge disappears after the message is persisted

Cause: `responseTimeMs` was stored top-level on the message; the backend's
`_normalize_chat` only preserves `role`, `content`, `responseData` — top-
level fields get stripped.

Fix: nest inside `responseData`. Read with the fallback pattern
`msg.responseData?.responseTimeMs ?? msg.responseTimeMs`.

### 7.5 Status endpoint spams the access log

Cause: polling every 1.5s while the doc indexes fires 40+ access-log rows
per upload.

Fix: the status endpoint MUST NOT call `_log_document_access` (or your
agent's equivalent). It's a lightweight polling endpoint, not a document
read.

### 7.6 Upload progress percent stays at 0

Cause: caller passed the upload to `fetch()` instead of the XHR-based
service function. `fetch()` can't report upload-side progress.

Fix: use the XHR-based `uploadHRDocument` pattern. Verify
`options.onProgress` is being passed through.

### 7.7 Two agents overwrite each other's FAISS index

Cause: same on-disk directory.

Fix: HR uses `hr_vector_indexes/`, Frontline uses
`frontline_vector_indexes/`. Your new agent should use
`<agent>_vector_indexes/`. Never share.

### 7.8 LLM answers still verbose after prompt tightening

Cause: the "no preamble" rule is in the system prompt but not the
knowledge prompt. LLMs weight the knowledge prompt more heavily because
it's closer to the actual generation.

Fix: put the seven rules (no preamble, no verbatim quotes, tight length,
etc.) in `get_knowledge_prompt`, not just the system prompt. See
[core/HR_agent/prompts.py:51-61](core/HR_agent/prompts.py#L51-L61).

### 7.9 Frontline vs HR response shape drift

Frontline's status endpoint returns `progress_percent`; HR returns
`percent`. The frontend handles both. If you pick either shape for the
new agent, the BackgroundUploadManager already supports it — see the
fallback in
[BackgroundUploadManager.jsx](PaPerProjectFront/src/components/shared/BackgroundUploadManager.jsx)
around the `poll` callback handling.

Prefer `percent` (shorter, matches HR).

---

## 8. Testing checklist

Run through this after porting to verify nothing regressed:

### Retrieval speed

- [ ] Upload a small doc (~5 pages). First query < 8s. Repeat query < 5s.
      Same question repeat < 1s (cache hit).
- [ ] Upload a large doc (100+ pages). First query < 15s (index build).
      Subsequent queries < 5s.
- [ ] Timing badge shows `path: faiss(...)`. If it shows `json_scan|
      scanned=...`, FAISS isn't loading.
- [ ] Ask a question that hits the answer cache twice. Second hit shows
      the green `cached` pill and total time < 200ms.

### Retrieval correctness

- [ ] Ask a question that's covered by the doc. Answer is grounded and
      cites the right source.
- [ ] Ask a question NOT covered by the doc. Response falls back to "I
      don't have verified information on this…" (not a hallucinated
      answer).
- [ ] Upload a doc with a TOC. Retrieval doesn't return TOC-line
      "citations" like `. . . . . . . 58`.
- [ ] Ask a small-talk question ("hey"). Response is graceful, not a
      confused dump of chunks.

### Upload UX

- [ ] Click Upload → toast fires immediately, dialog closes, pill appears
      bottom-right.
- [ ] Navigate to another tab while uploading. Come back — upload is
      still running.
- [ ] Upload two docs in a row. Both appear in the pill's expanded panel.
- [ ] Kill the network mid-upload. Pill shows "failed" state with the
      error message.
- [ ] Upload completes → toast fires + pill turns green + auto-dismisses
      after ~8s.

### Cache invalidation

- [ ] Ask a question → cache hit on repeat.
- [ ] Upload a new doc → previous cached answer is invalidated. Next same
      question rebuilds fresh (with the new doc's content available).

### Timing display

- [ ] Every response shows `⏱ Answered in X.Xs`.
- [ ] Responses over 1s show the `(retrieval Xs · llm Ys)` breakdown.
- [ ] Live clock ticks in the "thinking" spinner while waiting.

---

## 9. Appendix — file map

Reference files organised by concern:

### HR agent (canonical)

**Backend:**
- [hr_agent/chunking.py](hr_agent/chunking.py) — TOC filter
- [hr_agent/vector_store.py](hr_agent/vector_store.py) — FAISS per-company
- [hr_agent/tasks.py](hr_agent/tasks.py) — Celery processing + cache invalidation
- [hr_agent/management/commands/reindex_hr_documents.py](hr_agent/management/commands/reindex_hr_documents.py) — reindex CLI
- [core/HR_agent/services.py](core/HR_agent/services.py) — retrieval + caches + timing
- [core/HR_agent/hr_agent.py](core/HR_agent/hr_agent.py) — answer cache + timing bubble
- [core/HR_agent/prompts.py](core/HR_agent/prompts.py) — no-preamble rules
- [api/views/hr_agent.py](api/views/hr_agent.py) — Q&A + upload + status endpoints

**Frontend:**
- [PaPerProjectFront/src/services/hrAgentService.js](PaPerProjectFront/src/services/hrAgentService.js) — XHR upload + status poll
- [PaPerProjectFront/src/components/hr/HRDashboard.jsx](PaPerProjectFront/src/components/hr/HRDashboard.jsx) — dashboard integration
- [PaPerProjectFront/src/components/hr/HRKnowledgeQAAgent.jsx](PaPerProjectFront/src/components/hr/HRKnowledgeQAAgent.jsx) — Q&A UI with timing badge + ElapsedTimer
- [PaPerProjectFront/src/components/hr/HRFloatingChat.jsx](PaPerProjectFront/src/components/hr/HRFloatingChat.jsx) — floating chat

### Frontline agent (secondary reference)

- [Frontline_agent/chunking.py](Frontline_agent/chunking.py)
- [Frontline_agent/vector_store.py](Frontline_agent/vector_store.py)
- [Frontline_agent/tasks.py](Frontline_agent/tasks.py)
- [Frontline_agent/management/commands/reindex_documents.py](Frontline_agent/management/commands/reindex_documents.py)
- [core/Frontline_agent/services.py](core/Frontline_agent/services.py)
- [core/Frontline_agent/frontline_agent.py](core/Frontline_agent/frontline_agent.py)
- [core/Frontline_agent/prompts.py](core/Frontline_agent/prompts.py)
- [api/views/frontline_agent.py](api/views/frontline_agent.py)

### Shared frontend infrastructure

- [PaPerProjectFront/src/components/shared/BackgroundUploadManager.jsx](PaPerProjectFront/src/components/shared/BackgroundUploadManager.jsx) — global upload manager
- [PaPerProjectFront/src/components/frontline/chatShellUtils.jsx](PaPerProjectFront/src/components/frontline/chatShellUtils.jsx) — `ElapsedTimer` and other chat primitives
- [PaPerProjectFront/src/App.jsx](PaPerProjectFront/src/App.jsx) — provider mount point

### Companion docs

- [RAG_STRATEGY.md](RAG_STRATEGY.md) — architecture rationale, vector-DB comparison, when to graduate off FAISS
