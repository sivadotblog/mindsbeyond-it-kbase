# -----------------------------------------------------------------------------
# MongoDB Atlas Search Indexes for Knowledge Base
# -----------------------------------------------------------------------------
# This configuration creates:
# 1. A Full-Text Search index for keyword/hybrid search
# 2. A Vector Search index with auto-embeddings using Voyage AI voyage-context-4
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Full-Text Search Index
# -----------------------------------------------------------------------------
# This index enables full-text search capabilities for hybrid search.
# It indexes the raw_markdown, title, and other text fields.
# Can be combined with vector search for hybrid search queries.
# -----------------------------------------------------------------------------
resource "mongodbatlas_search_index" "fulltext_search_index" {
  project_id      = var.atlas_project_id
  cluster_name    = var.atlas_cluster_name
  database        = var.database_name
  collection_name = var.collection_name
  name            = "fulltext_index"
  type            = "search"

  # Search index definition using dynamic and static mappings
  mappings_dynamic = false

  mappings_fields = jsonencode({
    raw_markdown = {
      type         = "string"
      analyzer     = "lucene.standard"
      indexOptions = "offsets"
      store        = true
      norms        = "include"
    }
    title = {
      type         = "string"
      analyzer     = "lucene.standard"
      indexOptions = "offsets"
      store        = true
      norms        = "include"
    }
    category = {
      type     = "string"
      analyzer = "lucene.keyword"
    }
    domain = {
      type     = "string"
      analyzer = "lucene.standard"
    }
    doc_id = {
      type     = "string"
      analyzer = "lucene.keyword"
    }
    prerequisites = {
      type     = "string"
      analyzer = "lucene.standard"
    }
    "troubleshooting.error" = {
      type     = "string"
      analyzer = "lucene.standard"
    }
    "troubleshooting.solution" = {
      type     = "string"
      analyzer = "lucene.standard"
    }
  })
}

# -----------------------------------------------------------------------------
# Vector Search Index with Auto-Embedding (Voyage AI voyage-context-4)
# -----------------------------------------------------------------------------
# This index uses Atlas's auto-embedding feature to automatically generate
# embeddings for the raw_markdown field using the voyage-context-4 model.
# Supports semantic/vector search queries.
# -----------------------------------------------------------------------------
resource "mongodbatlas_search_index" "auto_embedding_index" {
  project_id      = var.atlas_project_id
  cluster_name    = var.atlas_cluster_name
  database        = var.database_name
  collection_name = var.collection_name
  name            = "auto_embedding_index"
  type            = "vectorSearch"

  fields = jsonencode([
    {
      type     = "autoEmbed"
      modality = "text"
      path     = "raw_markdown"
      model    = "voyage-4"
    },
    {
      type = "filter"
      path = "category"
    },
    {
      type = "filter"
      path = "domain"
    },
    {
      type = "filter"
      path = "metadata.source_id"
    }
  ])
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------
output "fulltext_search_index_id" {
  description = "ID of the full-text search index"
  value       = mongodbatlas_search_index.fulltext_search_index.index_id
}

output "auto_embedding_index_id" {
  description = "ID of the auto-embedding vector search index"
  value       = mongodbatlas_search_index.auto_embedding_index.index_id
}

output "index_names" {
  description = "Names of all created search indexes"
  value = {
    fulltext   = mongodbatlas_search_index.fulltext_search_index.name
    auto_embed = mongodbatlas_search_index.auto_embedding_index.name
  }
}
