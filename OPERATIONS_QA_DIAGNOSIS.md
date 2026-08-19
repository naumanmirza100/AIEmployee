# Operations Knowledge QA — "Sometimes Wrong Answers" Diagnosis

## TL;DR
Semantic (embedding-based) retrieval is **completely disabled** in this
environment, so the RAG runs on **keyword matching only**. Keyword-only
retrieval picks the wrong chunks — especially it lets the largest document win
on raw word frequency — which is exactly the "sometimes wrong answer" QA saw.

## Root cause chain
1. **`EMBEDDING_PROVIDER = 'groq'`** is hard-set in settings (not `auto`).
2. **Groq does not support an embeddings API** — the code itself says so
   (`embedding_service._init_groq`: *"Groq doesn't natively support embeddings API"*).
   So `_init_groq()` returns `False`.
3. Because the provider is **pinned to `groq`** (not `auto`), the service does
   **not** fall through to the other providers — even though `OPENROUTER_API_KEY`
   is set. `EmbeddingService.is_available()` ends up `False`.
4. **`sentence-transformers` is in `requirements.txt` (`>=3.0.0`) but not
   installed** in the venv, so the free/offline Local provider — the intended
   default and highest priority in `auto` mode — also can't load.
5. Net effect: **0 of 2109 chunks have embeddings**, semantic retrieval is
   skipped, and `_build_context` relies entirely on the keyword path.

## Evidence
- `EmbeddingService.is_available()` → **False** (log: *"No embedding provider available"*).
- Chunks with embeddings: **0 / 2109**.
- `import sentence_transformers` → `ModuleNotFoundError`.
- Settings: `EMBEDDING_PROVIDER=groq`, `GROQ_API_KEY` set, `OPENROUTER_API_KEY`
  set, `OPENAI_API_KEY`/`DEEPSEEK_API_KEY` not set.

## Observed wrong retrievals (keyword-only, real docs, company 10013)
- **"What is the vision of the university?"** — the vision text is literally the
  first chunk of the prospectus, but retrieval surfaced an unrelated
  *admission-committee* chunk (page 34) at the top. "vision" appears in many
  places; with no semantic ranking the right chunk didn't win.
- **"What technologies does the business plan use?"** — top source was the
  **prospectus** (wrong document), not the business plan. "technology" is
  frequent in the prospectus course list, so keyword frequency beat the correct
  doc. → **cross-document contamination**.
- Across every test the **largest document (prospectus, 1027 chunks)** dominated,
  because bigger docs contain each keyword more often → inflated keyword score.

## Why this produces "sometimes" wrong answers
Keyword retrieval works when the question's exact words appear in the right
chunk and nowhere misleading. It fails when:
- the answer uses synonyms (question "revenue" vs doc "sales"),
- a common word matches an unrelated but larger document,
- the correct chunk simply isn't in the keyword top-K because a bigger doc
  crowded it out.
The confidence gate + weak-match handling reduce blatant hallucination, but they
can't fix *which* chunks were retrieved.

## Recommended fix (in order)
1. **Enable a real embedding provider.** Cheapest + offline: install the Local
   model — `pip install sentence-transformers` (already in requirements) and set
   `EMBEDDING_PROVIDER=auto` (or `local`). This restores semantic retrieval with
   no API cost.
   - Alternatively point `EMBEDDING_PROVIDER` at a provider that actually serves
     an embeddings endpoint with a real embedding model (OpenAI
     `text-embedding-3-small`, etc.). Groq is not one.
2. **Backfill embeddings** for the existing 2109 chunks once a provider is live
   (re-run the embedding step / re-process, or a one-off backfill command).
3. **Harden the service (code):** when a *pinned* provider fails to initialise,
   fall through to the remaining providers instead of giving up — a pinned
   `groq` that can't do embeddings should not silently disable semantics when
   OpenRouter/Local are available.
4. **Keyword-path guard (defensive):** length-normalise the keyword score (per
   1k chars) so a large document can't win purely on size. Helps even when
   semantics are on, and is a safety net if embeddings are ever unavailable.
