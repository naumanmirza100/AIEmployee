# RAG Strategy for AIEmployee — Quick Reference

Answering the four questions you asked, in order.

---

## TL;DR

1. **What would I have to do to implement RAG?** Nothing new — you already have it. What we built IS a RAG system.
2. **Is what we did similar work?** Yes. Every fix we made (TOC filtering, embedding cache, prompt tuning, chunk-aware storage) is a RAG optimisation.
3. **Will RAG make it faster?** No. RAG *architecture* doesn't change latency. What makes it faster is: a real vector index, smaller prompts, caching, a faster LLM.
4. **Will a lot of docs need a lot of storage?** Yes, but not as much as you'd think — see the [storage math](#storage-math) below. And there are cheap options.

---

## What RAG actually is

RAG = **Retrieval-Augmented Generation**. Three steps:

1. **Ingest** — chop a document into chunks, turn each chunk into a vector (embedding), store the vectors.
2. **Retrieve** — turn the user's question into a vector, find the closest chunks by cosine similarity.
3. **Generate** — put those chunks into a prompt and ask an LLM to answer using them.

That's it. Everything else (re-ranking, filtering, hybrid search, caching) is optimisation on top.

---

## What we already have vs "full" RAG

You're already running a complete RAG pipeline. Here's the mapping:

| RAG step | HR agent | Frontline agent |
|----------|----------|-----------------|
| **Chunking** | `hr_agent/chunking.py` (section-aware + TOC filter) | `Frontline_agent/tasks.py` + `chunking.py` (sliding window + TOC filter) |
| **Embeddings** | `EmbeddingService` (OpenAI ada-002 or similar) | Same `EmbeddingService` |
| **Vector store** | Postgres/MSSQL row per chunk (`HRDocumentChunk.embedding` as JSON) | Same pattern (`DocumentChunk.embedding`) + optional **FAISS** index per company |
| **Retrieval** | Cosine over cached numpy vectors + keyword hybrid + RRF | FAISS-first, cosine fallback, keyword hybrid, RRF, LLM re-rank |
| **Generation** | `HRAgent.answer_question` → `_call_llm` | `FrontlineAgent.answer_question` → `_call_llm` |

**What "full-blown" RAG frameworks (LangChain, LlamaIndex) give you:**

- Pre-built loaders for 50+ file formats — we already have `DocumentProcessor`.
- Pre-built chunkers — we already have section-aware chunking.
- Pre-built retrievers — we already have hybrid search with RRF.
- Pre-built prompt templates — we already have `get_knowledge_prompt`.
- A wrapper around any vector DB — we could swap this in a day.

So the answer to "should we rewrite in LangChain?" is: **no benefit for this codebase.** LangChain is useful when you're prototyping; you're past prototyping.

---

## Is what we did the same as RAG work?

**Yes.** Everything we fixed in the last few days is textbook RAG optimisation:

| Fix we made | The RAG term for it |
|-------------|--------------------|
| TOC / dot-leader chunk filter | **Chunk quality filtering** — every RAG guide says "your retrieval is only as good as your chunks" |
| In-process embedding cache | **Vector cache** — standard optimisation |
| Query embedding cache | **Query cache** — same |
| Numpy cosine over Python cosine | **Vectorised similarity** — every real vector DB does this natively |
| Streaming DB iterator | **Batched retrieval** |
| Loosened HR prompt | **Prompt engineering** |
| Shorter excerpts + max_tokens | **Context window trimming** — one of the biggest latency levers |
| Section-aware chunking (HR) | **Semantic chunking** |
| Reciprocal Rank Fusion between semantic + keyword | **Hybrid search** — a huge quality lever |
| FAISS index (Frontline) | **Approximate Nearest Neighbour (ANN) index** |
| Upload/index progress UI | Just UX — but real RAG products do this too |

If you asked a RAG engineer to review the codebase, they'd say "yeah, that's a solid RAG system."

---

## Will RAG make it faster?

**Not by itself.** Retrieval is already fast (or can be with FAISS). The dominant costs, in order:

| Cost | Typical latency | Can RAG reduce it? |
|------|----------------|--------------------|
| **LLM generation** | 3–10 s (streaming) | No — but shorter prompts + fewer output tokens help (we did both) |
| **LLM re-ranking** (Frontline only) | 1–3 s | Yes — skip it when confidence is high, or use a cheaper reranker like `bge-reranker` locally |
| **Query embedding** | 200–800 ms | Cache it (we do) |
| **Vector similarity** | O(N) Python fallback = 500ms–5s for big docs; **FAISS = <10 ms**; **Pinecone / Qdrant = <30 ms** | Yes — installing FAISS or moving to a real vector DB is the biggest single win |
| **Database round-trip** | 5–50 ms | Column pruning, streaming (we do this) |

**Where the actual speed comes from:**

1. **Install FAISS** (`pip install faiss-cpu`). The Frontline agent already tries it. If it's not installed, you drop to the O(N) Python path — which is what we cached. But FAISS is faster than any cache.
2. **Use a smaller/faster LLM** for Q&A. `gpt-4o-mini`, `haiku-4.5`, or `groq/llama-3.1-8b-instant` cut LLM time in half.
3. **Trim excerpts** (done).
4. **Skip LLM re-rank** when hybrid search confidence is already high (Frontline currently always re-ranks).

---

## Storage math

Embeddings are just arrays of floating-point numbers. Concrete sizes:

| Model | Dimensions | Bytes per vector (float32) |
|-------|-----------|----------------------------|
| OpenAI `text-embedding-3-small` | 1536 | 6 KB |
| OpenAI `text-embedding-3-large` | 3072 | 12 KB |
| Cohere `embed-english-v3.0` | 1024 | 4 KB |
| Local `bge-small-en-v1.5` (free) | 384 | 1.5 KB |

For a **200-page PDF** at ~800 chars/chunk with 400 chunks:

- OpenAI small = 400 × 6 KB = **2.4 MB per doc**
- Local bge-small = 400 × 1.5 KB = **600 KB per doc**

Now scale it:

| Docs | OpenAI small | bge-small (local) |
|------|--------------|-------------------|
| 100 | 240 MB | 60 MB |
| 1,000 | 2.4 GB | 600 MB |
| 10,000 | 24 GB | 6 GB |
| 100,000 | 240 GB | 60 GB |

**Reality check:** even at 10,000 docs, 24 GB fits on the smallest AWS RDS/managed Postgres instance. You will not run out of storage before you run out of *retrieval quality* — long before storage matters, you'll need to worry about how a 100,000-vector FAISS index performs, and that's when you graduate to a dedicated vector DB.

**On disk, our current setup stores the vector as JSON text in a database column** — that's ~2–3× the binary size because JSON has commas and brackets. Moving to a dedicated vector store (or just `bytea` / `binary` columns) recovers that overhead.

---

## Vector store options — pros & cons

Ranked from "smallest change to your codebase" to "biggest change."

### 1. Stay on FAISS (what Frontline already uses)

**How it works:** On-disk index files per company, loaded into memory on demand. Free, open source, Facebook-maintained.

- ✅ Already integrated (Frontline). Zero new infrastructure.
- ✅ Fastest option for < 1M vectors per company.
- ✅ No monthly cost.
- ❌ Rebuild-on-write model — every new doc invalidates the whole index (we already handle this via `mark_index_dirty`).
- ❌ Not multi-writer safe — fine for our per-company model, but not if two workers write simultaneously.
- ❌ You manage backups yourself.

**Verdict:** Install `pip install faiss-cpu` on the server and this is done. Roll HR to the same pattern.

### 2. pgvector (Postgres extension)

**How it works:** A Postgres extension that adds a `vector` column type + ANN index (HNSW / IVFFlat).

- ✅ If you're on Postgres, no new service to run.
- ✅ Vectors live in the same DB as your rows — transactional, backups just work.
- ✅ Filter by metadata + vector similarity in one SQL query.
- ✅ Scales to ~10M vectors per index on decent hardware.
- ❌ Your current DB is **SQL Server** (based on the earlier SLA fix). pgvector needs Postgres.
- ❌ Adding Postgres just for embeddings is a real ops decision.

**Verdict:** Great option *if* you're willing to add Postgres. Otherwise skip.

### 3. Chroma DB

**How it works:** Self-hosted, embedded ("SQLite for vectors") or client-server. Uses DuckDB under the hood. First-class LangChain support.

- ✅ Trivially easy to set up — `pip install chromadb` and it runs.
- ✅ Nice Python API, works well with LangChain/LlamaIndex.
- ✅ Free, self-hosted, no vendor lock-in.
- ✅ Metadata filtering built in.
- ❌ Best for < 10M vectors. Beyond that, performance falls off.
- ❌ Newer project (v1.0 in 2024) — less battle-tested than FAISS.
- ❌ Persists to disk as its own format — another data location to back up.

**Verdict:** Good middle ground. If you dislike FAISS's rebuild-on-write model, Chroma solves that.

### 4. Qdrant

**How it works:** Rust-based vector database. Self-hosted (Docker) or cloud (Qdrant Cloud).

- ✅ Very fast, HNSW indexing, good filter performance.
- ✅ Rich filter language — combines metadata + similarity elegantly.
- ✅ Self-hostable → no vendor lock-in.
- ✅ Handles hundreds of millions of vectors comfortably.
- ❌ Another service to run + monitor.
- ❌ Overkill until you have >1M vectors.

**Verdict:** Best self-hosted option once you outgrow FAISS/Chroma.

### 5. Pinecone

**How it works:** Fully managed cloud vector database. Pay per pod (compute) + per GB stored.

- ✅ Zero ops — someone else runs it.
- ✅ Scales to billions of vectors.
- ✅ Very fast, geo-replicated.
- ✅ Simple Python SDK.
- ❌ Costs real money at scale ($70/mo minimum for a starter pod, more as you grow).
- ❌ Vendor lock-in — your embeddings live on their servers.
- ❌ Data leaves your infrastructure — compliance question for HR docs.
- ❌ Extra latency (network hop to their servers).

**Verdict:** Only if you don't want to run infrastructure and you have budget. **Note:** for HR documents (with confidentiality tiers `hr_only` etc.), sending embeddings to a third party may be a compliance no-go.

### 6. Weaviate

**How it works:** Similar to Qdrant — open source vector DB with a cloud option. GraphQL API.

- ✅ Feature-rich (built-in modules for OpenAI embeddings, hybrid search, etc.).
- ✅ Self-host or cloud.
- ❌ Heavier to run than Qdrant (JVM-based components).
- ❌ Learning curve on the GraphQL API.

**Verdict:** Competitive with Qdrant. Pick whichever the team likes.

### 7. Milvus

**How it works:** Enterprise-scale vector DB, Kubernetes-native.

- ✅ Handles billions of vectors, distributed.
- ✅ Very mature at scale.
- ❌ Complex to operate (needs etcd, MinIO, pulsar, etc.).
- ❌ Overkill for anything under a few million vectors.

**Verdict:** Only if you're doing web-scale RAG. Not you, not yet.

### 8. Elasticsearch / OpenSearch with dense_vector

**How it works:** ES/OpenSearch got dense-vector kNN support in recent versions.

- ✅ If you're already running ES for logs/search, adding vectors is one field type.
- ✅ Great hybrid search (BM25 + vectors) in one query.
- ❌ ES is heavy. Not worth standing up just for vectors.

**Verdict:** Only if ES is already in your stack.

---

## Recommendation for AIEmployee

Given where you are today:

1. **Now (this week):** Install `faiss-cpu` on the server. Frontline will immediately use it. Extend the same pattern to HR by mirroring Frontline's `vector_store` module.
2. **Soon (next quarter, when you cross ~500 uploaded docs per tenant):** Move to **Chroma** (self-hosted) or **Qdrant** (if you want more headroom).
3. **Later (only if you truly hit scale):** Pinecone or Milvus.

Do NOT:
- Rewrite the whole retrieval layer in LangChain/LlamaIndex "for RAG." You already have RAG; you'd just be adding an abstraction.
- Send HR embeddings to Pinecone without a compliance review.
- Switch vector DBs before you've measured a real problem — the biggest wins right now are still on the LLM side (smaller models, shorter prompts).

---

## What "faster" actually looks like (rank-ordered)

If you want the biggest single latency wins in order:

1. **Install FAISS** on the server (probably 5-10× faster retrieval on the JSON-scan path we cached).
2. **Switch to a faster LLM** for Q&A — `haiku-4.5` or `groq/llama-3.1-8b-instant` cut LLM time 30–60%.
3. **Skip the LLM re-rank step** when top-K semantic scores are already high (Frontline's `_llm_rerank` is a second LLM call).
4. **Cache the whole answer** by `(company_id, doc_scope, question_hash)` for repeat FAQ-style questions.
5. **Stream the LLM response** to the browser instead of waiting for the full answer — first-token latency drops from 4s → 0.5s perceived.

That's the roadmap.

---

# Part 2 — Scaling to many companies × many documents

The earlier sections answered "which vector DB should I use?" in the abstract. This section is the concrete plan for a multi-tenant SaaS with real scale ambitions.

## The prescription

**Deploy Qdrant as a Docker container. One collection per company. Migrate off FAISS + JSON-in-DB by the time you cross ~50 active tenants or 500 uploaded docs.**

That single sentence is the recommendation. The rest of this section is *why*.

## Why Qdrant, specifically

Compared to the alternatives at multi-tenant scale:

| Pick | Verdict for your case |
|------|----------------------|
| **Qdrant** ✅ | Best fit. Fast HNSW (Rust). Self-hosted. Handles hundreds of millions of vectors. Multi-tenancy via collections OR payload filtering. Free. One Docker container. Snapshots for backup. Cheap ops. |
| Chroma | Fine below ~10M vectors. Falls off at scale. Newer, less battle-tested. Good starter but you'd migrate off it. |
| Pinecone | ❌ Compliance risk for HR docs (embeddings leave your infra). Vendor lock-in. Recurring cost that grows with volume. |
| Weaviate | Competitive with Qdrant but heavier to run (JVM components). Pick Qdrant unless the team prefers GraphQL. |
| Milvus | Overkill unless you're already on Kubernetes and expecting billions of vectors. Runs etcd + MinIO + Pulsar — 4 services to operate. |
| pgvector | Great IF you're on Postgres. You're on SQL Server, so adding pgvector means adding a whole DB. Not a small decision. |
| FAISS (stay put) | Free, already integrated. Ceiling: single-writer, no built-in multi-tenancy, rebuild-on-write, no queryable metadata filters. Fine until ~1M vectors per company. |

## Multi-tenancy strategy — the important choice

You have two ways to isolate companies inside Qdrant:

### Option A: One collection per company *(recommended for you)*

- `company_1_kb`, `company_2_kb`, …
- Best data isolation — deleting a company = `DELETE /collections/company_N_kb`.
- Snapshots per-company for backups.
- Search is scoped by URL, no filter cost.
- **Ceiling: ~10,000 collections per Qdrant node.** If you're a B2B SaaS with <10k tenants (nearly all of them are), this is fine forever.
- **Slight overhead** per collection (memory + startup file handles).

### Option B: Shared collection + `payload_filter: {company_id: 42}`

- One collection: `documents`.
- Every point tagged with `{company_id, doc_id, visibility, doc_type}`.
- Search always includes `must` filter on `company_id`.
- **Scales to millions of tenants** — Instagram-like scale.
- **Deleting a tenant = filtered delete** — slower than dropping a collection.
- **Cross-tenant leakage risk** if you ever forget the filter (a single missing `must` clause = disaster).

**Pick Option A unless you're planning for >10k tenants.** For 10s-100s of B2B companies, per-collection is safer, faster to manage, and impossible to leak cross-tenant.

## Storage math at scale

Realistic ceilings for a mid-size B2B SaaS:

| Scenario | Vectors | Storage (OpenAI 1536-dim) | Storage (bge-small 384-dim, self-hosted) |
|----------|---------|---------------------------|-------------------------------------------|
| 10 companies × 100 docs each = 1k docs × 400 chunks | 400k | ~2.4 GB | ~0.6 GB |
| 100 companies × 500 docs each = 50k docs × 400 chunks | 20M | ~120 GB | ~30 GB |
| 1000 companies × 1000 docs each = 1M docs × 400 chunks | 400M | ~2.4 TB | ~600 GB |

Both HR and Frontline can share the same Qdrant instance (different collections). Even the biggest row fits on a $150/month bare-metal server. Qdrant supports:

- **On-disk vector storage** — memory-map the hot HNSW graph, keep vectors on SSD. 10× less RAM.
- **Scalar quantization** — 4× compression with minimal recall loss.
- **Product quantization** — 20-30× compression if you need to squeeze harder.

## The embedding choice becomes important at scale

At 400M vectors, embedding costs matter:

- **OpenAI `text-embedding-3-small`** — ~$0.02 / 1M tokens. Excellent quality. 1536-dim.
- **`bge-small-en-v1.5` (self-hosted)** — free after model download, ~15 ms/vector on CPU, 100 ms/vector batched. 384-dim (4× smaller storage). Recall almost as good.
- **`bge-large-en-v1.5`** — even better quality, 1024-dim, slower.

**At 100+ companies I'd host bge-small locally.** Embedding costs stop being a rounding error and self-hosting is a one-time setup. Ship it behind a `/embed` internal endpoint so both HR and Frontline agents call the same service.

## Migration path (concrete, in order)

Do these in this order — each step is independently useful and you can stop at any level:

### Step 1 (today, 1 hour) — Prove FAISS is actually running

Look at the Django startup log. You want to see:
```
Frontline vector store: FAISS active (O(log N) retrieval).
```
If you see the "NOT INSTALLED" warning, that Python venv isn't seeing `faiss-cpu`. Fix that first — no vector DB upgrade helps if FAISS isn't loading.

### Step 2 (this week, 4-8 hours) — Get HR on the same FAISS pattern

HR still uses O(N) Python cosine. Mirror `Frontline_agent/vector_store.py` into `hr_agent/vector_store.py`. This delays the "you need a real vector DB" conversation by 6-12 months.

### Step 3 (this quarter, 1-2 days) — Stand up Qdrant

- Run `docker run -p 6333:6333 -v $(pwd)/qdrant_data:/qdrant/storage qdrant/qdrant`
- Add `pip install qdrant-client` to requirements.
- Create a `core/vector_store/qdrant_client.py` adapter that mirrors the API shape of `Frontline_agent/vector_store.py`.
- Dual-write: on every doc upload, write to BOTH FAISS and Qdrant. Read from FAISS in production but instrument Qdrant reads in the background so you can compare recall/latency.
- After 2 weeks of no-issue dual-write, flip reads to Qdrant. Delete the FAISS index dir on next deploy.

### Step 4 (later, only if load demands) — Optimise Qdrant

- Enable on-disk storage (`hnsw_config.on_disk: true` on the collection).
- Enable scalar quantization for older/cold collections.
- Move Qdrant to its own VPS (or a small K8s deployment) once it's serving >100 QPS.
- Snapshots to S3 nightly.

### Step 5 (much later, only if truly needed) — Managed cloud or Qdrant Cloud

If ops burden becomes real, Qdrant Cloud offers the same product managed. Same API, same SDK — migration is trivial. Do this if you'd rather pay $200-500/month than have someone patch Docker containers.

## The uncomfortable truth about "scale"

Everything above is about retrieval scale. **Retrieval isn't your bottleneck today.** Your 130-160s query times are dominated by the LLM call, not the vector search. Even a perfect Qdrant setup won't make a 130-second LLM answer arrive faster.

So before you spend a week on Qdrant, ask:

1. Are queries actually slow because of retrieval? (Check the `timing_ms` breakdown we just added.)
2. Is FAISS actually loading? (Startup log check.)
3. What model is the LLM call using? (Might be GPT-4 base at 30 tokens/sec — switching to `gpt-4.1-mini` or `haiku-4.5` is a 5× speedup for zero infrastructure change.)
4. Are you streaming responses? (Perceived latency drops 5-10× even if wall-clock is the same.)

If retrieval genuinely is the bottleneck (say `timing_ms.retrieval > 3000` on typical queries), then yes, do the Qdrant migration. Otherwise, fix the LLM path first.

## Common mistakes to avoid

- **Rewriting everything in LangChain "for RAG."** You already have RAG. LangChain would add an abstraction layer without solving the actual latency problem.
- **Picking Pinecone because it's the most-Googled option.** Managed convenience, but you send HR embeddings to a third party — compliance no-go.
- **Building a "generic" vector store adapter before you actually need it.** Your first cut of Qdrant integration should be Qdrant-specific. Generalise later if you ever swap.
- **Storing embeddings as JSON strings in SQL Server.** You currently do this. It works but wastes 2-3× space and every read costs a JSON.parse. Qdrant + native `bytea`/`binary` format fixes this.
- **Rebuilding the FAISS index on every doc upload.** Currently the FAISS layer marks the index dirty on write and rebuilds on next read. Fine at your scale — but note that a Qdrant migration eliminates this entirely (incremental upserts).
- **One giant shared collection with millions of tenants and a filter.** Only pick this if you're actually at millions of tenants. Otherwise per-collection is safer.

## In one paragraph

Stand up Qdrant in Docker with one collection per company. Do it when you cross ~50 active tenants or ~500 uploaded documents, or if the `timing_ms.retrieval` breakdown starts consistently exceeding 3 seconds. Until then, ensure FAISS is actually loading in production (log check) and port the same FAISS pattern to HR. The bigger latency win today is fixing the LLM path (model choice, streaming, prompt size), not the vector store.

