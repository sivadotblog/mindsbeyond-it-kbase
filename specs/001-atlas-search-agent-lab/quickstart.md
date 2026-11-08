# Quickstart: Atlas Search Lab, SOP Agent and Agent Memory

## 1. Offline, no cluster, no keys

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
KBASE_MODE=offline python app.py
```

Open http://localhost:5001/lab.html. Every result is labeled offline. Search uses BM25 and TF-IDF
cosine over `md_docs/` as stand ins for Atlas, and shows the pipeline Atlas would run.

## 2. Against Atlas

`.env`:

```env
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/
DB_NAME=kbase
COLLECTION_NAME=content
```

1. `python app.py`, open http://localhost:5001, Admin tab, Generate Data (loads 50 articles and
   creates `fulltext_index` and `auto_embedding_index`).
2. Open http://localhost:5001/lab.html. The status bar shows the server version and which methods
   are available.
3. Memory tab, Set up memory indexes (creates `agent_memory` indexes and the TTL index). Wait until
   the explorer shows the indexes as ready.

Cluster needs: M10+, storage auto scaling on (automated embedding), MongoDB 8.0+ for rank fusion,
8.3+ for score fusion, Native Reranking enabled in Project Settings for rerank.

## 3. Optional LLM

```env
LLM_PROVIDER=anthropic          # or openai
LLM_API_KEY=...
LLM_MODEL=claude-sonnet-5-5     # any model your provider serves
# openai compatible only:
LLM_BASE_URL=https://<resource>.openai.azure.com/openai/v1
LLM_AUTH_HEADER=api-key         # Azure style; default is Authorization: Bearer
```

## 4. Optional Atlas Agent Engine memory

```bash
pip install -e ".[agent-engine]"
```

```env
AGENTIC_MEMORY_PROJECT_ID=<agent engine project id>
# either a ready token
AGENTIC_MEMORY_SERVICE_ACCOUNT_TOKEN=<token>
# or client credentials, exchanged for a 1 hour token on demand
MDB_CLIENT=mdb_sa_id_...
MDB_SECRET=mdb_sa_sk_...
```

The Memory tab then lists `agent_engine` as a backend.

## 5. Demo script (SOP and memory)

1. User id `siva`. SOP Agent tab, task: "private endpoint connection keeps timing out".
2. The agent recalls nothing yet, shows candidates, picks KB-0016 and builds the checklist.
3. Tell the agent: "our cluster is kbase-prod". Mark step 2 failed with note "needed port 10260
   open on the NSG". Read the troubleshooting guidance. Mark the rest done. Finish.
4. Memory tab: one episode, one semantic fact (`cluster = kbase-prod`), one procedural note on
   KB-0016 step 2.
5. Start a new run: "nc to the private endpoint fails on 10260". The plan shows the recalled fact,
   note and episode with score parts.

## 6. Live smoke from GitHub Actions

Repository settings already hold `MDB_CLIENT` (variable) and `MDB_SECRET` (secret). Optionally add
variables `ATLAS_PROJECT_ID` and `ATLAS_CLUSTER_NAME`. The service account needs Project Owner (or
Project Database Access Admin plus Project Network Access Manager) on the project, and its API
access list must allow GitHub runners or be empty.

Actions tab, `live-smoke`, Run workflow. The job summary has the capability report and a pass, fail
or unsupported line per method. The temporary user and access entry are deleted at the end and
expire on their own after `ttl_hours`.

## 7. Tests

```bash
pytest                 # unit tests, all I/O mocked
pytest --cov           # with the coverage gate
```
