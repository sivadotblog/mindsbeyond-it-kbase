# Mindsbeyond IT Knowledge Base

A MongoDB Atlas-powered knowledge base application featuring vector search, hybrid search, and AI reranking capabilities. Built with Flask and designed for enterprise IT documentation.

## Features

- **50 Generated IT Knowledge Articles** - Comprehensive documentation covering MongoDB Atlas, Azure integration, Terraform, Kafka, and more
- **Vector Search** - Semantic search using MongoDB Atlas auto-embeddings with Voyage AI (`voyage-4`)
- **Hybrid Search** - Combined vector + full-text search using `$rankFusion` for best-of-both-worlds results
- **AI Reranking** - Post-retrieval reranking with `$rerank` stage using `rerank-2.5-lite` for improved relevance
- **Admin Panel** - Generate data and reset demo with real-time status updates
- **Terraform Integration** - Infrastructure-as-Code option for search index creation

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────────────┐
│   Frontend      │────▶│   Flask API     │────▶│   MongoDB Atlas         │
│   (HTML/CSS/JS) │     │   (Python)      │     │   - Auto-embeddings     │
└─────────────────┘     └─────────────────┘     │   - Vector Search       │
                                                │   - Full-text Search    │
                                                │   - Reranking           │
                                                └─────────────────────────┘
```

## Prerequisites

- Python 3.11+
- MongoDB Atlas cluster (M10+ for vector search, M30+ recommended for reranking)
- Atlas cluster running MongoDB 8.0+ (8.3+ for `$rerank`)
- Native Reranking enabled in Atlas Project Settings (for rerank feature)

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/sivadotblog/mindsbeyond-it-kbase.git
   cd mindsbeyond-it-kbase
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Configure environment variables**
   
   Create a `.env` file in the project root:
   ```env
   MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
   DB_NAME=kbase
   COLLECTION_NAME=content
   ```

5. **Run the application**
   ```bash
   python app.py
   ```
   
   The app will be available at http://localhost:5001

## Usage

### Web Interface

1. Open http://localhost:5001 in your browser
2. Navigate to the **Admin** tab
3. Click **Generate Data** to create sample articles and search indexes
4. Switch to the **Articles** tab to browse and search

### Search Features

- **Vector Search**: Enter a natural language query and click "Vector Search" for semantic matching
- **Hybrid Search**: Click "Hybrid Search" to combine vector and keyword matching
- **Rerank**: Check the "Rerank" checkbox to apply AI reranking for improved relevance

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/articles` | GET | List articles with pagination |
| `/api/articles/<doc_id>` | GET | Get a single article |
| `/api/search` | GET | Vector search (`?q=query&limit=10&rerank=true`) |
| `/api/search/hybrid` | GET | Hybrid search (`?q=query&limit=10&rerank=true`). Uses `fulltext_index` for the text leg (it used to name `content_search_index`, which is never created). |
| `/api/admin/generate` | POST | Generate sample data and indexes |
| `/api/admin/reset` | POST | Reset database and indexes |

## KB Lab: search methods, SOP agent and agent memory

Open http://localhost:5001/lab.html. It has three tabs. The design, research and task list are in
[`specs/001-atlas-search-agent-lab/`](specs/001-atlas-search-agent-lab/), written with
[Spec Kit](https://github.com/github/spec-kit). Project rules are in
[`.specify/memory/constitution.md`](.specify/memory/constitution.md).

**Search lab.** Runs one question through several Atlas retrieval methods side by side and shows
each method's results, scores, time and exact pipeline. A rank river shows where methods agree, and
an overlap table gives Jaccard scores and ANN recall against exact search.

| Method | Stage | Needs |
|---|---|---|
| Full text (BM25) | `$search` | `fulltext_index` |
| Vector ANN | `$vectorSearch` on the `autoEmbed` field | `auto_embedding_index` |
| Vector ENN (exact) | `$vectorSearch` with `exact: true` | `auto_embedding_index` |
| Vector with pre filter | `$vectorSearch` with `filter` on category or domain | `auto_embedding_index` |
| Hybrid, rank fusion | `$rankFusion` (reciprocal rank fusion) | MongoDB 8.0+ |
| Hybrid, score fusion | `$scoreFusion` (sigmoid, minMaxScaler or none) | MongoDB 8.3+ |
| Rerank, on any method | `$rerank` with Voyage rerank models | Native Reranking enabled in Project Settings |

Methods the cluster cannot run show the reason instead of failing.

**SOP agent.** Describe a task. The agent recalls memory, finds the procedure with hybrid search
plus rerank, and turns the article into a checklist. It does the read only steps itself (search,
read, explain a command, check memory). Anything that runs a command or needs a credential is your
step: you mark it done, failed or skipped, and failures get troubleshooting guidance. The agent never
asks for secrets and redacts anything that looks like one. A trace shows every read, decision and
write in order.

**Memory.** Five memory types: short term (turns, expire by TTL), episodic (run summaries),
semantic (labeled facts), procedural (notes tied to a procedure step) and taxonomic (domain terms).
Recall scores combine relevance, recency and importance, and the explorer shows each part. New facts
are consolidated: same label and value is NOOP, a new value is UPDATE with history, anything else
is ADD. Three backends:

- `atlas`: `kbase.agent_memory` with an `autoEmbed` vector index, a text index and a TTL index.
  Recall is one `$rankFusion` over vector, text and "recent and important" inputs. Press Set up
  memory indexes once.
- `agent_engine`: the Atlas Agent Engine memory service (public preview), through
  `agent-engine-sdk-memory`. Install with `pip install -e ".[agent-engine]"` and set
  `AGENTIC_MEMORY_PROJECT_ID` plus either `AGENTIC_MEMORY_SERVICE_ACCOUNT_TOKEN` or `MDB_CLIENT`
  and `MDB_SECRET`.
- `inmemory`: in the app process, used offline and in tests.

**Offline mode.** With no `MONGODB_URI` (or `KBASE_MODE=offline`) everything runs on the files in
`md_docs/` with Python stand ins for the Atlas methods, and results are labeled offline.

**LLM, optional.** The agent works without a model. Set `LLM_PROVIDER=anthropic` or `openai` (any
OpenAI compatible endpoint, such as Azure AI Foundry) with `LLM_API_KEY`, and optionally
`LLM_MODEL`, `LLM_BASE_URL` and `LLM_AUTH_HEADER`, to let a model choose the procedure, extract facts
and write run summaries. Any bad reply falls back to the rules.

### API v2

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v2/health`, `/api/v2/capabilities`, `/api/v2/facets` | GET | Mode, cluster support, filter values |
| `/api/v2/search/methods` | GET | Methods and their requirements |
| `/api/v2/search` | POST | Run one method |
| `/api/v2/search/compare` | POST | Run several methods and measure agreement |
| `/api/v2/agent/runs` | GET, POST | List runs, start a run |
| `/api/v2/agent/runs/<id>` | GET | Read a run with its checklist and trace |
| `/api/v2/agent/runs/<id>/choose`, `/steps/<step>`, `/messages`, `/finish` | POST | Drive a run |
| `/api/v2/memory` | GET, POST | List or write memories |
| `/api/v2/memory/search` | POST | Recall with score parts |
| `/api/v2/memory/<id>` | DELETE | Delete a memory |
| `/api/v2/memory/backends`, `/api/v2/memory/setup` | GET, POST | Backends and index setup |

The full contract is in
[`contracts/openapi.yaml`](specs/001-atlas-search-agent-lab/contracts/openapi.yaml).

### GitHub Actions

- `ci.yml` runs the unit tests and the coverage gate on every push and pull request. Every Atlas,
  HTTP and LLM call is mocked.
- `live-smoke.yml` is manual (Actions tab, Run workflow). It uses the Atlas service account in
  `vars.MDB_CLIENT` and `secrets.MDB_SECRET`. A service account can only call the Atlas
  Administration API, so the job creates a temporary database user and a temporary IP access entry
  for the runner (both with `deleteAfterDate`), seeds data, builds indexes, checks every method,
  memory and one agent run, writes a report to the job summary, and deletes the user and entry in
  an always run step. Optional variables: `ATLAS_PROJECT_ID`, `ATLAS_CLUSTER_NAME`, `DB_NAME`,
  `AGENTIC_MEMORY_PROJECT_ID`, `LLM_PROVIDER`; optional secret `LLM_API_KEY`. The service account
  needs Project Owner, or Project Database Access Admin plus Project Network Access Manager, and its
  own API access list must allow GitHub runners.

## Search Index Configuration

### Full-Text Search Index (`fulltext_index`)
```json
{
  "mappings": {
    "fields": {
      "raw_markdown": { "type": "string", "analyzer": "lucene.standard" },
      "title": { "type": "string", "analyzer": "lucene.standard" },
      "category": { "type": "string", "analyzer": "lucene.keyword" },
      "domain": { "type": "string", "analyzer": "lucene.standard" }
    }
  }
}
```

### Auto-Embedding Vector Index (`auto_embedding_index`)
```json
{
  "fields": [
    {
      "type": "autoEmbed",
      "modality": "text",
      "path": "raw_markdown",
      "model": "voyage-4"
    },
    { "type": "filter", "path": "category" },
    { "type": "filter", "path": "domain" }
  ]
}
```

## Terraform Setup (Optional)

For infrastructure-as-code index management:

1. Copy the example tfvars file:
   ```bash
   cp terraform/terraform.tfvars.example terraform/terraform.tfvars
   ```

2. Fill in your Atlas credentials in `terraform/terraform.tfvars`

3. Enable "Use Terraform" checkbox in the Admin panel, or run manually:
   ```bash
   cd terraform
   terraform init
   terraform apply
   ```

## Testing

Run the test suite:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=. --cov-report=html
```

Run integration tests (requires running server):
```bash
pytest -m integration
```

## Project Structure

```
mindsbeyond-it-kbase/
├── app.py                 # Flask API application
├── generate_kbase.py      # Document generation script
├── static/
│   └── index.html         # Frontend UI
├── md_docs/               # Generated markdown documents
├── terraform/             # Terraform configurations
│   ├── providers.tf
│   ├── variables.tf
│   ├── search_indexes.tf
│   └── terraform.tfvars.example
├── tests/
│   ├── test_app.py
│   └── test_generate_kbase.py
├── .cursorrules           # TDD development guidelines
├── pyproject.toml         # Python project configuration
└── README.md
```

## Technologies

- **Backend**: Flask, PyMongo 4.17+
- **Database**: MongoDB Atlas
- **Search**: Atlas Search, Atlas Vector Search
- **Embeddings**: Voyage AI (voyage-4 for indexing, voyage-4-lite for queries)
- **Reranking**: MongoDB Native Reranking (rerank-2.5-lite)
- **Infrastructure**: Terraform (optional)
- **Testing**: pytest

## License

MIT License
