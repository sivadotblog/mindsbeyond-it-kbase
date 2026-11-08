# Implementation Plan: Atlas Search Lab, SOP Agent and Agent Memory

**Branch**: `feat/atlas-search-agent-lab` | **Date**: 2026-11-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-atlas-search-agent-lab/spec.md`

## Summary

Add a `kbase` Python package next to the existing Flask app. It has three parts that share one
Atlas connection:

1. **Search Lab**: pure functions that build the aggregation pipeline for each retrieval method
   (`$search`, `$vectorSearch` ANN and ENN with autoEmbed, filtered vector, `$rankFusion`,
   `$scoreFusion`, and a `$rerank` tail), a service that runs one or many of them and measures
   agreement, and a capability probe that explains what the cluster supports.
2. **SOP Agent**: a small agent engine (tools, trace, LLM port, memory hooks) and an SOP runner that
   finds a procedure with hybrid search plus rerank, turns the article into a checklist, runs the
   safe steps itself and waits for a human on the rest.
3. **Agent Memory**: one `MemoryStore` interface with three backends (Atlas collections with an
   autoEmbed index and `$rankFusion` retrieval, Atlas Agent Engine memory service, in process).
   Memory has five types and every read returns relevance, recency and importance parts.

A new single page UI (`static/lab.html`, `static/lab.js`, `static/lab.css`) drives all three through
new `/api/v2` endpoints. Two GitHub workflows are added: unit tests on every push, and a manual live
smoke run that uses the Atlas service account in `MDB_CLIENT` and `MDB_SECRET`.

## Technical Context

**Language/Version**: Python 3.11+ (raised from 3.10 because the Agent Engine memory SDK needs 3.11).
JavaScript ES2020 in the browser, no build step.

**Primary Dependencies**: Flask, PyMongo 4.13+, python-dotenv, requests. Optional extra
`agent-engine`: `agent-engine-sdk-memory>=0.11`. LLM providers are called over HTTPS with
`requests`, so no LLM SDK is required.

**Storage**: MongoDB Atlas. Existing `kbase.content` collection and its `fulltext_index` and
`auto_embedding_index`. New collections `kbase.agent_memory` and `kbase.agent_runs`. Offline mode
reads `md_docs/*.md` and keeps runs and memory in process.

**Testing**: pytest, pytest-mock, pytest-cov. All Atlas, HTTP and LLM calls mocked. Live checks are
`integration` marked and run by `kbase.smoke` in the manual workflow.

**Target Platform**: Linux or macOS developer machine, and GitHub Actions `ubuntu-latest`.

**Project Type**: Web service with a static single page front end.

**Performance Goals**: one method under 2 s, six method compare under 5 s on 50 articles (SC-002).
Compare runs methods in a small thread pool.

**Constraints**: works offline (Constitution V); never handles secrets in agent paths
(Constitution IV); pipelines are pure and returned with every result (Constitution II).

**Scale/Scope**: 50 articles, tens of memories per user, single tenant demo.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How the plan complies | Status |
|---|---|---|
| I. Atlas does the AI work | Embedding (autoEmbed), fusion and reranking are pipeline stages. Offline mode approximates them in Python and labels results `offline`. The only external model calls are the optional LLM for agent reasoning, which is not KB retrieval. | Pass |
| II. Show the work | `SearchResult.pipeline`, `Run.trace`, `MemoryHit.score_parts` and the memory retrieval pipeline are part of every response and rendered in the UI. | Pass |
| III. Test first, mock I/O | Pipeline builders are pure and unit tested for shape. Services take injected collections and HTTP sessions. Live tests only in `kbase.smoke`. | Pass |
| IV. Credentials off the agent | No agent tool executes commands. Command steps are human steps. Notes go through `redact()` before storage. Secret like variables are never filled from memory. Workflow masks the generated password. | Pass |
| V. Works offline, degrades clearly | `KBASE_MODE=offline` or no `MONGODB_URI` selects offline search, in process runs and memory. Unsupported Atlas features return `unsupported` with the requirement. | Pass |
| VI. Keep it simple | No front end framework. One new package with small modules. One optional dependency. | Pass |

Post design re-check (after Phase 1): still passes. The only added complexity is the memory backend
interface with three implementations, which the spec requires (FR-022).

## Project Structure

### Documentation (this feature)

```text
specs/001-atlas-search-agent-lab/
├── plan.md              # This file
├── research.md          # Phase 0: deep research on search methods, memory, SOP agents, auth
├── data-model.md        # Phase 1: entities and collections
├── quickstart.md        # Phase 1: run it locally and from GitHub Actions
├── contracts/
│   └── openapi.yaml     # Phase 1: /api/v2 contract
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2
```

### Source Code (repository root)

```text
app.py                      # existing Flask app; registers the v2 blueprint; hybrid index fix
generate_kbase.py           # existing generator, unchanged
kbase/
├── __init__.py
├── config.py               # Settings from env (mode, index names, models, LLM, memory backend)
├── container.py            # builds and caches services for the app
├── api.py                  # Flask blueprint /api/v2
├── redact.py               # secret redaction
├── search/
│   ├── pipelines.py        # pure pipeline builders per method
│   ├── methods.py          # method registry: params, requirements, builder
│   ├── service.py          # SearchService: run, compare, capabilities (Atlas)
│   ├── offline.py          # OfflineSearchService over md_docs (BM25, TF-IDF cosine, RRF)
│   ├── compare.py          # agreement metrics
│   └── docs.py             # markdown article parser shared with the SOP parser
├── agent/
│   ├── llm.py              # LLM port: offline, anthropic, openai compatible
│   ├── trace.py            # Trace and TraceEvent
│   ├── engine.py           # AgentEngine: tools, memory hooks, trace
│   ├── sop.py              # article to checklist, actor classification, hints
│   ├── sop_agent.py        # SOPAgent: start, choose, confirm, message, finish
│   └── runs.py             # RunStore: Mongo and in process
├── memory/
│   ├── models.py           # MemoryRecord, MemoryHit, ScoreParts, MemoryType
│   ├── scoring.py          # recency decay and combined score
│   ├── base.py             # MemoryStore protocol and errors
│   ├── inmemory.py         # in process backend
│   ├── atlas.py            # Atlas backend: indexes, $rankFusion recall pipeline, TTL
│   ├── agent_engine.py     # Atlas Agent Engine memory service adapter
│   ├── extract.py          # fact and note extraction (heuristic, LLM optional)
│   └── consolidate.py      # ADD / UPDATE / NOOP decisions
├── atlas_admin.py          # service account token, discovery, temporary access, cleanup, CLI
└── smoke.py                # live capability and smoke report, CLI
static/
├── index.html              # existing; adds a link to the lab
├── lab.html
├── lab.js
└── lab.css
tests/
├── test_app.py, test_generate_kbase.py         # existing
├── test_search_pipelines.py, test_search_service.py, test_search_offline.py, test_compare.py
├── test_llm.py, test_sop.py, test_sop_agent.py, test_engine.py, test_runs.py, test_redact.py
├── test_memory_scoring.py, test_memory_inmemory.py, test_memory_atlas.py,
│   test_memory_agent_engine.py, test_memory_consolidate.py
├── test_atlas_admin.py, test_smoke.py, test_api_v2.py, test_config.py
.github/workflows/
├── ci.yml                  # unit tests on push and pull request
└── live-smoke.yml          # manual live run with MDB_CLIENT and MDB_SECRET
```

**Structure Decision**: single project. The new `kbase` package sits beside the existing modules so
the current app, tests and Terraform keep working. The front end stays static files served by
Flask.

## Key Design Decisions

1. **autoEmbed query shape**: `$vectorSearch.query` is sent as `{"text": "..."}` with an optional
   `model`, matching the stage reference and `pymongo-search-utils`. The existing app sends a plain
   string. The builder takes a `query_format` setting (`object` default, `string` fallback) and the
   service retries once with the other shape if the server rejects the first, then remembers it.
2. **Rerank is a tail, not an input**: `$rerank` cannot run inside `$rankFusion` or `$scoreFusion`
   inputs, so every method can append `$addFields: preRerankScore`, `$rerank`, `$addFields: score`.
   The service computes rank deltas by running the base pipeline and the reranked pipeline.
3. **Capabilities are probed, not assumed**: `buildInfo` gives the version, `list_search_indexes`
   gives index status. `$scoreFusion` and `$rerank` are also probed with a tiny query on first use
   and cached, because preview gating is per project.
4. **Memory recall is one `$rankFusion`** with three inputs: autoEmbed vector search, full text
   `$search`, and a `$match` plus `$sort` on importance and recency. After fusion, `$addFields`
   computes recency with `$dateDiff` and `$exp`, normalizes the fused score with
   `$setWindowFields`, and builds the weighted score. The pipeline is returned with the hits.
5. **Agent steps never execute commands**. Agent actions are: search the KB, read an article, recall
   memory, explain a command, check a prerequisite is documented, write memory. The LLM is optional
   and always has a deterministic fallback.
6. **Service account use is CI only**: `kbase.atlas_admin` mints an Atlas Admin API token, finds the
   project and cluster, creates a database user with `deleteAfterDate` and an access list entry with
   `deleteAfterDate`, then deletes both in an always run step. The same client id and secret can
   mint an Agent Engine token when `AGENTIC_MEMORY_PROJECT_ID` is set.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Three memory backends behind one interface | FR-022: offline demo, self built Atlas memory, and Atlas Agent Engine memory | A single Atlas backend would break offline mode and would not show Agent Engine |
