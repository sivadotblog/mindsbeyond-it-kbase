# Data Model: Atlas Search Lab, SOP Agent and Agent Memory

## Collections

| Collection | Owner | Purpose |
|---|---|---|
| `kbase.content` | existing | Knowledge base articles. Unchanged. |
| `kbase.agent_runs` | new | SOP runs with checklist and trace. |
| `kbase.agent_memory` | new | Agent memory, all five types in one collection. |

### `kbase.content` (existing, read only for this feature)

```text
doc_id         string   "KB-0016"
title          string
category       string   "How-To Guide" | "Tutorial"   (filter field)
domain         string   (filter field)
prerequisites  string
steps          { step1, step2, verify }   command strings
troubleshooting{ error, solution }
metadata       { source_id, cost_center, framework }
raw_markdown   string   (autoEmbed path and full text path)
```

Indexes: `fulltext_index` (search), `auto_embedding_index` (vectorSearch, autoEmbed voyage-4).

### `kbase.agent_runs`

```text
_id            string   run id (uuid4 hex)
user_id        string
task           string   redacted
status         "choosing" | "no_match" | "in_progress" | "completed" | "abandoned"
created_at, updated_at   datetime (UTC)
search         { method, query, candidates: [ {doc_id, title, score, norm_score} ] }
procedure      { doc_id, title, reason, chosen_by: "agent" | "user" } | null
recalled       [ MemoryHit ]          memories used when planning
checklist      [ ChecklistStep ]
messages       [ { role, content, at } ]   redacted
trace          [ TraceEvent ]
summary        string | null
memory_writes  [ { op: "ADD"|"UPDATE"|"NOOP", type, label, id } ]
```

Index: `{user_id: 1, updated_at: -1}`.

**ChecklistStep**

```text
id         "pre-1" | "step-1" | "step-2" | "verify" | "agent-related" | ...
kind       "prerequisite" | "step" | "verify" | "agent"
actor      "agent" | "human"
title      string
command    string | null          shown, never executed
explain    string                 what the command does (agent or LLM)
hints      [ string ]             from procedural notes and semantic facts
status     "pending" | "done" | "failed" | "skipped"
note       string | null          redacted
guidance   [ string ]             troubleshooting added on failure
output     string | null          result of an agent step
```

State rules: agent steps complete automatically when the run starts. A human step moves from
`pending` to `done`, `failed` or `skipped` by confirmation. A failed step stays failed and gets
`guidance`. The run is `completed` when finished by the user and `abandoned` when finished with
pending steps.

**TraceEvent**

```text
seq       int (1..n)
at        datetime
kind      "memory_recall" | "search" | "decision" | "tool" | "confirm" | "message"
          | "memory_write" | "llm" | "llm_fallback" | "warning"
title     string
detail    object                 pipeline, scores, tool args, decisions
ms        float | null
```

### `kbase.agent_memory`

```text
_id         string (uuid4 hex)
type        "stm" | "episodic" | "semantic" | "procedural" | "taxonomic"
user_id     string
agent_id    string | null        "sop-agent"
visibility  "private" | "org"
label       string | null        semantic key, taxonomic term, procedural key "KB-0016:step-2"
label_key   string | null        normalized label for consolidation
content     string               autoEmbed and full text path
importance  float 0..1
source      { run_id, doc_id, step_id } | null
history     [ { content, at } ]  previous values for UPDATE
created_at, updated_at   datetime
expires_at  datetime | null      set for stm, TTL index
```

Indexes:

- `memory_vector_index` (vectorSearch): `autoEmbed` on `content` with `voyage-4`, filters `user_id`,
  `type`, `visibility`, `agent_id`.
- `memory_text_index` (search): `content` and `label` with `lucene.standard`; `user_id`, `type`,
  `visibility` as `token`.
- TTL: `{expires_at: 1}` with `expireAfterSeconds: 0`.
- Lookup: `{user_id: 1, type: 1, label_key: 1}`.

Visibility rule: a read for user U returns records where `user_id == U` or `visibility == "org"`.

## API shapes

**SearchRequest**: `query` (1..1000 chars), `method`, `limit` (1..50, default 10), `num_candidates`,
`query_model`, `filters {category?, domain?}`, `weights {vector, text}`, `normalization`,
`rerank` (bool), `rerank_model`, `fuzzy` (bool).

**SearchResult**: `method`, `label`, `status` ("ok" | "unsupported" | "error"), `reason`,
`offline` (bool), `results [ {rank, doc_id, title, category, domain, score, pre_rerank_rank?,
rank_change?, score_details?} ]`, `pipeline`, `ms`, `warnings [string]`.

**CompareResult**: `query`, `results {method: SearchResult}`, `agreement {pairs: [{a, b, jaccard,
common}], consensus: [{doc_id, title, methods, avg_rank}]}`.

**MemoryHit**: `record` (MemoryRecord without history), `score`, `score_parts {relevance, recency,
importance}`, `why` (string).

**MemoryRecallResult**: `backend`, `hits [MemoryHit]`, `pipeline | null`, `ms`.
