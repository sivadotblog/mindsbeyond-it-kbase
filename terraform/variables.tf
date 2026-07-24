# -----------------------------------------------------------------------------
# Variables for MongoDB Atlas Search Index Configuration
# -----------------------------------------------------------------------------

variable "atlas_public_key" {
  description = "MongoDB Atlas Programmatic API Public Key"
  type        = string
  sensitive   = true
}

variable "atlas_private_key" {
  description = "MongoDB Atlas Programmatic API Private Key"
  type        = string
  sensitive   = true
}

variable "atlas_project_id" {
  description = "MongoDB Atlas Project ID"
  type        = string
}

variable "atlas_cluster_name" {
  description = "MongoDB Atlas Cluster Name"
  type        = string
}

variable "database_name" {
  description = "Database name for the knowledge base"
  type        = string
  default     = "kbase"
}

variable "collection_name" {
  description = "Collection name for the knowledge base content"
  type        = string
  default     = "content"
}

variable "embedding_model" {
  description = "Voyage AI embedding model to use for auto-embeddings"
  type        = string
  default     = "voyage-context-4"
}
