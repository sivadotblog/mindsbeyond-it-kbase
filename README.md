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

- Python 3.8+
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
   pip install flask pymongo python-dotenv
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
| `/api/search/hybrid` | GET | Hybrid search (`?q=query&limit=10&rerank=true`) |
| `/api/admin/generate` | POST | Generate sample data and indexes |
| `/api/admin/reset` | POST | Reset database and indexes |

## Search Index Configuration

### Full-Text Search Index (`content_search_index`)
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
