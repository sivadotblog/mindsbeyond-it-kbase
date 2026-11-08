# Research: Atlas Search Lab, SOP Agent and Agent Memory

**Date**: 2026-11-08. Sources were read on this date. Preview features change, so each decision
below says where the request shape lives in code.

## 0. Audit of the existing setup

What is there today:

- `generate_kbase.py` writes 50 markdown SOP style articles to `md_docs/` and upserts them into
  `kbase.content` with structured fields (`prerequisites`, `steps.step1`, `steps.step2`,
  `steps.verify`, `troubleshooting.error`, `troubleshooting.solution`) and the full `raw_markdown`.
- `app.py` creates two indexes: `fulltext_index` (Atlas Search, `lucene.standard` on title and body,
  keyword on category) and `auto_embedding_index` (Vector Search, `autoEmbed` on `raw_markdown` with
  `voyage-4`, filters on `category`, `domain`, `metadata.source_id`).
- `/api/search` runs `$vectorSearch` with `voyage-4-lite` at query time and an optional `$rerank`
  with `rerank-2.5-lite`. `/api/search/hybrid` runs `$rankFusion` over vector and text.

Findings that this feature fixes or works around:

1. **Hybrid search points at an index that is never created.** The text leg of `$rankFusion` uses
   `content_search_index`, but both the PyMongo path and Terraform create `fulltext_index`.
   `$search` on a missing index returns no documents, so the hybrid result is vector only.
   Decision: the v2 builders use the configured `KBASE_TEXT_INDEX` (default `fulltext_index`), and
   the v1 endpoint is fixed to use the same name.
2. **autoEmbed query shape.** The `$vectorSearch` stage reference lists `query` as an object with a
   `text` field for autoEmbed fields, and MongoDB's own `pymongo-search-utils` sends
   `"query": {"text": query}`. The existing app sends a plain string, which an older overview page
   also shows. Decision: send the object form by default, retry once with the string form if the
   server rejects it, and cache the shape that works.
3. **Querying with `voyage-4-lite` against a `voyage-4` index is valid.** All voyage-4 family models
   share an embedding space, and the stage accepts a `model` override that must be compatible with
   the index model.
4. `terraform/variables.tf` declares `embedding_model` with default `voyage-context-4`, but the
   resource hard codes `voyage-4`, and Terraform uses programmatic API keys rather than a service
   account. Left as is in this feature, noted for a follow up.

## 1. Retrieval methods in Atlas

### 1.1 Full text (`$search`)

Lucene BM25 over analyzed fields. Best for exact identifiers, error codes and rare words (for
example `CANNOT_DOWNGRADE_BELOW_STORAGE` or `10260`). Score read with `{"$meta": "searchScore"}`.

Decision: `text` operator on `title` and `raw_markdown`, optional `fuzzy` (maxEdits 1), and
category or domain filters through `compound.filter` with `equals` on keyword fields. Builder:
`kbase/search/pipelines.py::fulltext_stage`.

### 1.2 Vector search with automated embedding (`$vectorSearch` + `autoEmbed`)

- The index field type is `autoEmbed` with `modality: "text"`, `path` and `model`. Filter fields use
  `type: "filter"`. Optional `numDimensions` (256, 512, 1024, 2048), `similarity` and `quantization`
  (`float`, `scalar`, `binary`, `binaryNoRescore`).
- Atlas embeds documents on write and the query text at query time. Embeddings live in a generated
  collection in an internal database. Dedicated clusters must have storage auto scaling on, or the
  index goes stale when the disk fills.
- Models and price per million tokens: `voyage-4-lite` $0.02, `voyage-4` $0.06 (recommended),
  `voyage-4-large` $0.12, `voyage-code-4` $0.12.
- Query: `{"$vectorSearch": {"index", "path", "query": {"text": ...}, "model"?, "numCandidates" |
  "exact": true, "limit", "filter"?}}`. Score: `{"$meta": "vectorSearchScore"}`.
- Automated Embedding is a Preview feature. Embedding inference runs on Google Cloud regardless of
  the cluster's cloud.

### 1.3 ANN versus ENN

- ANN uses HNSW. `numCandidates` sets the priority queue size, must be at most 10,000 and at least
  `limit`. MongoDB recommends starting at 20 times `limit` and tuning for recall.
- ENN (`exact: true`) scans every vector. Recommended when measuring ANN recall, when the collection
  has under 10,000 documents, or when a selective pre filter leaves under 5% of the data.
- With quantization on, ENN uses the full fidelity vectors.

Decision: the lab runs ANN and ENN as two methods and reports their overlap as "ANN recall at k".
With 50 articles both should agree, which is itself a useful teaching point.

### 1.4 Pre filters

`$vectorSearch.filter` supports `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`, `$exists`,
`$not`, `$nor`, `$and`, `$or` on fields indexed as `filter`. Pre filtering does not change the score
and is usually slower than an unfiltered query. Decision: "filtered vector" exposes category and
domain, the two filter fields the existing index has.

### 1.5 Hybrid by rank: `$rankFusion` (MongoDB 8.0+)

- Reciprocal Rank Fusion: score is the sum over pipelines of `weight * 1 / (60 + rank)`. 60 is fixed.
- Input pipelines must be selection and ranking pipelines (start with `$search`, `$vectorSearch` or
  have a `$sort`) and must not modify documents. Names cannot start with `$` or contain `.`.
- `scoreDetails: true` sets per pipeline rank and weight, read with `{"$meta": "scoreDetails"}`.
- On 8.0.x it needs a support case. Fully available from 8.1.

### 1.6 Hybrid by score: `$scoreFusion` (MongoDB 8.3+)

- Combines scores, not ranks. `input.normalization` is `none`, `sigmoid` or `minMaxScaler`.
  `combination.method` is `avg` (default, with `weights`) or `expression` (custom arithmetic using
  `$$pipelineName`). `scoreDetails` reports raw and normalized values per pipeline.
- Useful when one retriever is much more confident than the other, which RRF hides.

Decision: lab exposes `normalization` and the two weights. Default `sigmoid`, weights 1 and 1.

### 1.7 Native reranking: `$rerank` (Preview)

- Syntax: `{"$rerank": {"query": {"text"}, "path": "<field>" | [...], "numDocsToRerank": <=1000,
  "model"}}`. Models: `rerank-2.5`, `rerank-2.5-lite`, and on dedicated clusters with 9.0+
  `rerank-3`, `rerank-3-lite`.
- Requires Atlas, Native Reranking enabled in Project Settings, and a recent server. The public
  preview launched 2026-07-01 on 8.3 auto upgrade clusters, and the current reference lists 9.0.
- Not allowed inside `$rankFusion` or `$scoreFusion` inputs, on views, or with client side field
  level encryption. Fails if a `path` field is missing on any input document.
- It replaces `{"$meta": "score"}`, so the earlier score must be copied into a field first.
- The LangGraph store docs warn that when the prerequisites are missing, reranked scores come back
  as one constant value instead of an error. Decision: the service flags a reranked result set
  where every score is equal.

Decision: rerank is an optional tail on any method: `$addFields {preRerankScore}`, `$limit`,
`$rerank` on `["title", "raw_markdown"]`, `$addFields {score}`, `$limit`. The compare view runs the
base and reranked pipelines and shows each article's rank change.

### 1.8 Lexical prefilters (`$search.vectorSearch`), deferred

Launched 2026-01-15. Lets a vector search be pre filtered with any Atlas Search operator (fuzzy,
phrase, wildcard, queryString). It needs `vector` fields in a `search` type index, which the existing
autoEmbed index is not. Out of scope for this feature; listed as a follow up.

## 2. Agent memory

### 2.1 Taxonomy

Most current designs use the same split, drawn from cognitive science:

| Type | Holds | Lifetime | Our store |
|---|---|---|---|
| Short term (working) | turns of the current run | hours, TTL | `type: stm`, `expires_at` TTL |
| Episodic | what happened in a past run and how it ended | months | `type: episodic` |
| Semantic | labeled facts ("cluster = kbase-prod") | until changed | `type: semantic`, keyed by label |
| Procedural | how to do something, notes tied to a procedure step | long | `type: procedural`, keyed by doc and step |
| Taxonomic | domain terms ("SourceID", "Nexus") | long, shared | `type: taxonomic`, visibility `org` |

Atlas Agent Engine uses the same four long term types (semantic, episodic, procedural, taxonomic)
plus short term memory, so the backends line up one to one.

### 2.2 Retrieval scoring

The Generative Agents paper (Park et al., 2023, arXiv:2304.03442) scores memories by a weighted sum
of relevance, recency (exponential decay) and importance. Mem0 also describes recency decay as
`exp(-lambda * dt)`. Decision: `score = w_rel * relevance + w_rec * recency + w_imp * importance`,
with relevance normalized to 0..1 inside the result set, recency `= 0.5 ** (age_hours /
half_life_hours)` and importance set at write time. Defaults 0.6, 0.2, 0.2 and a 7 day half life. All
three parts are returned.

On Atlas the whole calculation runs in the aggregation pipeline (`$rankFusion` for relevance,
`$dateDiff` and `$exp` for recency, `$setWindowFields` to normalize), so the explorer can show the
pipeline.

### 2.3 Writing and consolidation

- Mem0 (Chhikara et al., 2025, arXiv:2504.19413) extracts candidate facts with an LLM and decides
  ADD, UPDATE, DELETE or NOOP against similar existing memories. Reviews of the current open source
  code note it has since moved to ADD only extraction to avoid destructive mistakes, at the cost of
  more duplicates.
- Decision: semantic facts are keyed by a normalized label. Same label and same value is NOOP. Same
  label and a new value is UPDATE with the previous value kept in `history`. A new label is ADD
  unless a near duplicate exists (similarity above 0.9), which is NOOP. No automatic DELETE: users
  delete from the explorer. Each decision is written to the trace.
- Extraction is heuristic by default (patterns like "our X is Y", "X = Y", "remember that ...") and
  uses the LLM when one is configured.
- Forgetting: short term memory expires through a TTL index, as the TTL article in this knowledge
  base describes. Episodes are the consolidated form of a run.

### 2.4 MongoDB options looked at

- **LangGraph Checkpointer and Store on MongoDB**: short term via checkpoints, long term via
  `MongoDBStore` with autoEmbed support. Good, but brings LangChain and LangGraph into a demo that
  does not otherwise need them. Rejected for this feature, linked in the docs as an alternative.
- **Atlas Agent Engine memory** (public preview since 2026-09-29): a managed memory service with
  short term turns, background snapshot and LLM extraction into semantic, episodic, procedural and
  taxonomic memory, `build_context` and `build_context_from_sources` (per source text, semantic or
  hybrid mode, rerank, token budget), and private or org visibility. Reads combine `user_id` and
  `visibility` with AND, never OR, so shared plus personal needs two reads. Python SDK
  `agent-engine-sdk-memory` (Python 3.11+, depends only on httpx and pydantic). Hosted mode takes a
  service account access token minted at `https://agentengine.mongodb.com/api/v1/oauth/token` with
  client id and secret, plus a project id. The HTTP API is create only for procedures and the SDK
  has no delete. Decision: adapter backend `agent_engine`, used when `AGENTIC_MEMORY_PROJECT_ID` and
  a token or client credentials are set. Delete is reported as not supported.
- **Self built on Atlas**: one `agent_memory` collection with an autoEmbed vector index and a text
  index. Decision: default backend when connected to Atlas, because it shows every pipeline.

## 3. SOP agents

- SOP-Agent (Ye et al., 2025, arXiv:2501.09316) represents an SOP as a decision graph and limits the
  tools the agent may call at each node to the ones that node allows. It reports better robustness
  than general agents.
- Decision: each knowledge base article becomes a linear checklist (prerequisites, step 1, step 2,
  verify) with a troubleshooting branch taken when a step fails. Each step has an allowed tool set.
  Command steps are human steps. Agent steps are read only: search, read article, recall memory,
  explain, check that a prerequisite is documented.
- Choosing the SOP: hybrid search plus rerank with a fallback chain (hybrid plus rerank, hybrid,
  vector, full text, offline). If the top candidate's normalized score is below a threshold, the
  agent stops and shows candidates instead of starting a checklist (spec edge case).
- Hints from memory: a procedural note for the same article and step is shown on that step. A
  semantic fact whose label matches a variable in a command (for example `$CLUSTER`) is shown as a
  hint, except for secret like names (`KEY`, `SECRET`, `PASS`, `TOKEN`), which are never filled.

## 4. Credentials and live checks

- Atlas service accounts use OAuth 2.0 client credentials at `https://cloud.mongodb.com/api/oauth/
  token` and return a one hour bearer token. They reach only the Administration API, never cluster
  data. A service account can have its own API access list, which can block GitHub runner IPs.
- To read data in CI, the workflow creates a temporary database user (`deleteAfterDate`, scoped to
  the cluster, `readWrite` and `dbAdmin` on `kbase`) and a temporary IP access list entry
  (`deleteAfterDate`) for the runner's public IP, then deletes both in an always run step. Both
  also expire on their own if the job is killed.
- The workflow reads `vars.MDB_CLIENT` and `secrets.MDB_SECRET`. Project and cluster come from
  workflow inputs or `vars.ATLAS_PROJECT_ID` and `vars.ATLAS_CLUSTER_NAME`, else they are discovered
  when the service account sees exactly one.
- Atlas Agent Engine's CLI also takes Atlas service account credentials, so the same pair can mint
  an Agent Engine token if the service account has access to the Agent Engine project.

## 5. LLM

Provider neutral port with three implementations: `offline` (deterministic, default), `anthropic`
(Messages API over HTTPS, default model `claude-sonnet-5-5`) and `openai` (any OpenAI compatible
`/chat/completions` endpoint, including Azure AI Foundry). The agent asks for JSON, validates it,
and falls back to the deterministic path on any error, writing a `llm_fallback` trace event.

## 6. Spec Kit

Spec Kit 1.3.x installs as Claude Code skills in `.claude/skills/speckit-*` and keeps templates and
scripts in `.specify/`. Flow used here: constitution, specify (with recorded clarifications), plan
(this research, data model, contracts, quickstart), tasks, analyze, implement.

## Sources

- Automated Embedding overview: https://www.mongodb.com/docs/vector-search/crud-embeddings/automated-embedding.md
- `$vectorSearch` stage: https://www.mongodb.com/docs/vector-search/query/aggregation-stages/vector-search-stage.md
- `$rerank` stage: https://www.mongodb.com/docs/vector-search/query/aggregation-stages/rerank/
- Native Reranking quick start: https://www.mongodb.com/docs/vector-search/query/native-reranking/quickstart/
- Native Reranking public preview: https://www.mongodb.com/products/updates/now-in-public-preview-native-reranking-rerank-on-atlas/
- `$rankFusion`: https://www.mongodb.com/docs/manual/reference/operator/aggregation/rankfusion/
- `$scoreFusion`: https://www.mongodb.com/docs/manual/reference/operator/aggregation/scorefusion/
- Lexical prefilters: https://mongodb.com/company/blog/product-release-announcements/semantic-power-lexical-precision-advanced-filtering-for-vector-search
- `vectorSearch` Atlas Search operator: https://www.mongodb.com/docs/search/query/operators-collectors/vectorsearch/
- `pymongo-search-utils` 0.3.1 and `langchain-mongodb` 0.12.1 source (autoEmbed and rerank stage builders)
- LangGraph and MongoDB: https://www.mongodb.com/docs/atlas/ai-integrations/langgraph
- Atlas Agent Engine memory types: https://www.mongodb.com/docs/agentengine/add-features/memory-types/
- Agent Engine memory SDK: https://www.mongodb.com/docs/agentengine/sdk/python/packages/agent-engine-sdk-memory/ and the `agent-engine-sdk-memory` 0.11.13 README on PyPI
- Agent Engine launch: https://mongodb.com/company/newsroom/press-releases/mongodb-launches-atlas-agent-engine-to-put-ai-agents-in-production-without-a-new-stack
- Atlas API authentication and service accounts: https://mongodb.com/docs/atlas/api/api-authentication/
- SOP-Agent: https://arxiv.org/abs/2501.09316
- Mem0: https://arxiv.org/abs/2504.19413
- Generative Agents: https://arxiv.org/abs/2304.03442
- Spec Kit: https://github.com/github/spec-kit
