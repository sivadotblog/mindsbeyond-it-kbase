"""Flask API for the Knowledge Base application."""
import os
import math
import subprocess
from flask import Flask, jsonify, request
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from pymongo.operations import SearchIndexModel
from dotenv import load_dotenv

# Import generation functions from generate_kbase
from generate_kbase import generate_markdown_files, insert_into_mongodb

# Load environment variables
load_dotenv()

# MongoDB configuration
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "kbase")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "content")

# Global client (lazy initialization)
_client = None
_db = None
_collection = None


def get_client():
    """Get the MongoDB client, initializing if needed."""
    global _client
    
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    
    return _client


def get_db():
    """Get the MongoDB database, initializing connection if needed."""
    global _db
    
    if _db is None:
        client = get_client()
        _db = client[DB_NAME]
    
    return _db


def get_collection():
    """Get the MongoDB collection, initializing connection if needed."""
    global _collection
    
    if _collection is None:
        db = get_db()
        _collection = db[COLLECTION_NAME]
    
    return _collection


def reset_connection():
    """Reset the global connection state (used after dropping collection)."""
    global _client, _db, _collection
    _client = None
    _db = None
    _collection = None


# Search Index Definitions
SEARCH_INDEX_DEFINITION = {
    "name": "fulltext_index",
    "definition": {
        "mappings": {
            "dynamic": False,
            "fields": {
                "raw_markdown": {
                    "type": "string",
                    "analyzer": "lucene.standard"
                },
                "title": {
                    "type": "string",
                    "analyzer": "lucene.standard"
                },
                "category": {
                    "type": "string",
                    "analyzer": "lucene.keyword"
                },
                "domain": {
                    "type": "string",
                    "analyzer": "lucene.standard"
                },
                "doc_id": {
                    "type": "string",
                    "analyzer": "lucene.keyword"
                }
            }
        }
    }
}

# Auto-embedding vector search index using Voyage AI
# Using voyage-4 (recommended for balanced performance)
VECTOR_INDEX_DEFINITION = {
    "name": "auto_embedding_index",
    "definition": {
        "fields": [
            {
                "type": "autoEmbed",
                "modality": "text",
                "path": "raw_markdown",
                "model": "voyage-4"
            },
            {
                "type": "filter",
                "path": "category"
            },
            {
                "type": "filter",
                "path": "domain"
            },
            {
                "type": "filter",
                "path": "metadata.source_id"
            }
        ]
    }
}


def create_search_indexes():
    """Create search and vector search indexes on the collection."""
    results = {"search": False, "vector": False, "search_error": None, "vector_error": None}
    
    try:
        collection = get_collection()
        
        # Create full-text search index
        try:
            collection.create_search_index(SEARCH_INDEX_DEFINITION)
            results["search"] = True
        except OperationFailure as e:
            # Index might already exist
            if "already exists" in str(e).lower():
                results["search"] = True
            else:
                results["search_error"] = str(e)
                print(f"Error creating search index: {e}")
        
        # Create vector search index (auto-embedding) using SearchIndexModel with type
        try:
            vector_model = SearchIndexModel(
                definition=VECTOR_INDEX_DEFINITION["definition"],
                name=VECTOR_INDEX_DEFINITION["name"],
                type="vectorSearch"
            )
            collection.create_search_index(model=vector_model)
            results["vector"] = True
        except OperationFailure as e:
            # Index might already exist
            if "already exists" in str(e).lower():
                results["vector"] = True
            else:
                results["vector_error"] = str(e)
                print(f"Error creating vector index: {e}")
                
    except Exception as e:
        print(f"Error creating indexes: {e}")
        
    return results


def delete_search_indexes():
    """Delete all search indexes from the collection."""
    try:
        collection = get_collection()
        
        # Get list of search indexes
        try:
            indexes = list(collection.list_search_indexes())
            for index in indexes:
                index_name = index.get("name")
                if index_name:
                    try:
                        collection.drop_search_index(index_name)
                    except Exception as e:
                        print(f"Error dropping index {index_name}: {e}")
        except Exception as e:
            print(f"Error listing indexes: {e}")
            
        return True
    except Exception as e:
        print(f"Error deleting indexes: {e}")
        return False


def run_terraform_apply():
    """Run Terraform to create search indexes."""
    terraform_dir = os.path.join(os.path.dirname(__file__), "terraform")
    
    try:
        # Check if terraform directory exists
        if not os.path.exists(terraform_dir):
            return {"success": False, "output": "Terraform directory not found"}
        
        # Check if terraform.tfvars exists
        tfvars_path = os.path.join(terraform_dir, "terraform.tfvars")
        if not os.path.exists(tfvars_path):
            return {"success": False, "output": "terraform.tfvars not found. Copy terraform.tfvars.example and fill in your credentials."}
        
        # Run terraform init (in case it hasn't been initialized)
        init_result = subprocess.run(
            ["terraform", "init", "-input=false"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if init_result.returncode != 0:
            return {"success": False, "output": f"Terraform init failed: {init_result.stderr}"}
        
        # Run terraform apply
        apply_result = subprocess.run(
            ["terraform", "apply", "-auto-approve", "-input=false"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if apply_result.returncode != 0:
            return {"success": False, "output": f"Terraform apply failed: {apply_result.stderr}"}
        
        return {"success": True, "output": apply_result.stdout}
        
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Terraform operation timed out"}
    except FileNotFoundError:
        return {"success": False, "output": "Terraform CLI not found. Please install Terraform."}
    except Exception as e:
        return {"success": False, "output": f"Terraform error: {str(e)}"}


def run_terraform_destroy():
    """Run Terraform to destroy search indexes."""
    terraform_dir = os.path.join(os.path.dirname(__file__), "terraform")
    
    try:
        if not os.path.exists(terraform_dir):
            return {"success": False, "output": "Terraform directory not found"}
        
        # Run terraform destroy
        destroy_result = subprocess.run(
            ["terraform", "destroy", "-auto-approve", "-input=false"],
            cwd=terraform_dir,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if destroy_result.returncode != 0:
            return {"success": False, "output": f"Terraform destroy failed: {destroy_result.stderr}"}
        
        return {"success": True, "output": destroy_result.stdout}
        
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Terraform operation timed out"}
    except FileNotFoundError:
        return {"success": False, "output": "Terraform CLI not found. Please install Terraform."}
    except Exception as e:
        return {"success": False, "output": f"Terraform error: {str(e)}"}


def create_app(testing: bool = False) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config["TESTING"] = testing

    @app.route("/api/articles", methods=["GET"])
    def list_articles():
        """List articles with pagination."""
        try:
            # Parse pagination parameters
            try:
                page = int(request.args.get("page", 1))
                if page < 1:
                    return jsonify({"error": "Page must be a positive integer"}), 400
            except ValueError:
                return jsonify({"error": "Invalid page parameter"}), 400

            try:
                per_page = int(request.args.get("per_page", 10))
                if per_page < 1:
                    return jsonify({"error": "per_page must be a positive integer"}), 400
                # Cap at 50 maximum
                per_page = min(per_page, 50)
            except ValueError:
                return jsonify({"error": "Invalid per_page parameter"}), 400

            collection = get_collection()
            
            # Get total count
            total = collection.count_documents({})
            total_pages = math.ceil(total / per_page) if total > 0 else 0

            # Calculate skip offset
            skip = (page - 1) * per_page

            # Fetch documents (exclude raw_markdown for list view)
            cursor = collection.find(
                {},
                {"_id": 0, "raw_markdown": 0}
            ).skip(skip).limit(per_page)

            articles = list(cursor)

            return jsonify({
                "articles": articles,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": total_pages,
                }
            })

        except ConnectionFailure:
            return jsonify({"error": "Database connection failed"}), 500

    @app.route("/api/articles/<doc_id>", methods=["GET"])
    def get_article(doc_id: str):
        """Get a single article by doc_id."""
        try:
            collection = get_collection()
            
            # Find article by doc_id, exclude MongoDB _id
            article = collection.find_one(
                {"doc_id": doc_id},
                {"_id": 0}
            )

            if article is None:
                return jsonify({"error": f"Article {doc_id} not found"}), 404

            return jsonify(article)

        except ConnectionFailure:
            return jsonify({"error": "Database connection failed"}), 500

    @app.route("/api/search", methods=["GET"])
    def search_articles():
        """Search articles using vector search with auto-embedding."""
        try:
            # Get and validate query parameter
            query = request.args.get("q", "").strip()
            if not query:
                return jsonify({"error": "Query parameter 'q' is required"}), 400
            
            # Get optional limit parameter
            try:
                limit = int(request.args.get("limit", 10))
                limit = min(max(limit, 1), 50)  # Between 1 and 50
            except ValueError:
                limit = 10
            
            # Check if reranking is requested
            rerank = request.args.get("rerank", "false").lower() == "true"
            
            collection = get_collection()
            
            # Vector search pipeline using autoEmbed
            # The query text is embedded using voyage-4-lite at query time
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "auto_embedding_index",
                        "path": "raw_markdown",
                        "query": query,
                        "model": "voyage-4-lite",
                        "numCandidates": limit * 10,
                        "limit": limit * 2 if rerank else limit
                    }
                }
            ]
            
            # Add rerank stage if requested
            # Note: Requires MongoDB 8.3+ and Native Reranking enabled in Atlas Project Settings
            if rerank:
                pipeline.append({
                    "$rerank": {
                        "model": "rerank-2.5-lite",
                        "query": {
                            "text": query
                        },
                        "numDocsToRerank": limit * 2,
                        "path": ["raw_markdown", "title"]
                    }
                })
                pipeline.append({
                    "$addFields": {
                        "score": {"$meta": "score"}
                    }
                })
                pipeline.append({"$limit": limit})
                pipeline.append({
                    "$project": {
                        "_id": 0,
                        "doc_id": 1,
                        "title": 1,
                        "category": 1,
                        "domain": 1,
                        "score": 1
                    }
                })
            else:
                pipeline.append({
                    "$project": {
                        "_id": 0,
                        "doc_id": 1,
                        "title": 1,
                        "category": 1,
                        "domain": 1,
                        "score": {"$meta": "vectorSearchScore"}
                    }
                })
            
            results = list(collection.aggregate(pipeline))
            
            return jsonify({
                "query": query,
                "results": results,
                "count": len(results),
                "pipeline": pipeline,
                "search_type": "vector",
                "reranked": rerank
            })
            
        except OperationFailure as e:
            return jsonify({"error": f"Search failed: {str(e)}"}), 500
        except ConnectionFailure:
            return jsonify({"error": "Database connection failed"}), 500

    @app.route("/api/search/hybrid", methods=["GET"])
    def hybrid_search():
        """Hybrid search using $rankFusion to combine vector and text search."""
        try:
            # Get and validate query parameter
            query = request.args.get("q", "").strip()
            if not query:
                return jsonify({"error": "Query parameter 'q' is required"}), 400
            
            # Get optional limit parameter
            try:
                limit = int(request.args.get("limit", 10))
                limit = min(max(limit, 1), 50)
            except ValueError:
                limit = 10
            
            # Check if reranking is requested
            rerank = request.args.get("rerank", "false").lower() == "true"
            
            collection = get_collection()
            
            # Hybrid search pipeline using $rankFusion
            pipeline = [
                {
                    "$rankFusion": {
                        "input": {
                            "pipelines": {
                                "vectorSearch": [
                                    {
                                        "$vectorSearch": {
                                            "index": "auto_embedding_index",
                                            "path": "raw_markdown",
                                            "query": query,
                                            "model": "voyage-4-lite",
                                            "numCandidates": limit * 10,
                                            "limit": limit * 2
                                        }
                                    }
                                ],
                                "textSearch": [
                                    {
                                        "$search": {
                                            "index": "content_search_index",
                                            "text": {
                                                "query": query,
                                                "path": ["title", "raw_markdown"]
                                            }
                                        }
                                    },
                                    {"$limit": limit * 2}
                                ]
                            }
                        },
                        "combination": {
                            "weights": {
                                "vectorSearch": 1.0,
                                "textSearch": 3.0
                            }
                        },
                        "scoreDetails": True
                    }
                },
                {"$limit": limit * 2 if rerank else limit}
            ]
            
            # Add rerank stage if requested
            # Note: Requires MongoDB 8.3+ and Native Reranking enabled in Atlas Project Settings
            if rerank:
                pipeline.append({
                    "$rerank": {
                        "model": "rerank-2.5-lite",
                        "query": {
                            "text": query
                        },
                        "numDocsToRerank": limit * 2,
                        "path": ["raw_markdown", "title"]
                    }
                })
                pipeline.append({
                    "$addFields": {
                        "score": {"$meta": "score"}
                    }
                })
                pipeline.append({"$limit": limit})
                pipeline.append({
                    "$project": {
                        "_id": 0,
                        "doc_id": 1,
                        "title": 1,
                        "category": 1,
                        "domain": 1,
                        "score": 1
                    }
                })
            else:
                pipeline.append({
                    "$project": {
                        "_id": 0,
                        "doc_id": 1,
                        "title": 1,
                        "category": 1,
                        "domain": 1,
                        "score": {"$meta": "score"}
                    }
                })
            
            results = list(collection.aggregate(pipeline))
            
            return jsonify({
                "query": query,
                "results": results,
                "count": len(results),
                "pipeline": pipeline,
                "search_type": "hybrid",
                "reranked": rerank
            })
            
        except OperationFailure as e:
            return jsonify({"error": f"Hybrid search failed: {str(e)}"}), 500
        except ConnectionFailure:
            return jsonify({"error": "Database connection failed"}), 500

    @app.route("/api/admin/reset", methods=["POST"])
    def reset_demo():
        """Reset the demo by deleting indexes and dropping the collection."""
        steps = []
        
        try:
            # Step 1: Delete search indexes
            delete_search_indexes()
            steps.append("✓ Indexes deleted")
            
            # Step 2: Drop the collection
            db = get_db()
            db.drop_collection(COLLECTION_NAME)
            steps.append("✓ Collection dropped")
            
            # Reset connection state
            reset_connection()

            return jsonify({
                "message": "Successfully reset demo.",
                "status": "success",
                "steps": steps
            })

        except OperationFailure as e:
            return jsonify({"error": f"Database operation failed: {str(e)}", "steps": steps}), 500
        except Exception as e:
            return jsonify({"error": f"Reset failed: {str(e)}", "steps": steps}), 500

    @app.route("/api/admin/generate", methods=["POST"])
    def generate_data():
        """Generate markdown files, create indexes, and load data into MongoDB."""
        steps = []
        
        # Check if Terraform option is enabled
        data = request.get_json(silent=True) or {}
        use_terraform = data.get("use_terraform", False)
        
        try:
            # Reset connection to ensure fresh state
            reset_connection()
            
            # Step 1: Generate markdown files
            generate_markdown_files()
            steps.append("✓ Markdown files generated")
            
            # Step 2: Insert documents into MongoDB
            insert_into_mongodb()
            steps.append("✓ 50 documents loaded into MongoDB")
            
            # Step 3 & 4: Create indexes (PyMongo or Terraform)
            if use_terraform:
                # Use Terraform to create indexes
                tf_result = run_terraform_apply()
                if tf_result.get("success"):
                    steps.append("✓ Terraform: Search indexes created")
                else:
                    steps.append(f"⚠ Terraform: {tf_result.get('output', 'Unknown error')}")
            else:
                # Use PyMongo to create indexes
                index_results = create_search_indexes()
                if index_results.get("search"):
                    steps.append("✓ Full-text search index created (PyMongo)")
                else:
                    error_msg = index_results.get("search_error", "Unknown error")
                    steps.append(f"⚠ Full-text search index failed: {error_msg}")
                    
                if index_results.get("vector"):
                    steps.append("✓ Auto-embedding index created (PyMongo)")
                else:
                    error_msg = index_results.get("vector_error", "Unknown error")
                    steps.append(f"⚠ Auto-embedding index failed: {error_msg}")

            return jsonify({
                "message": "Successfully generated data and created indexes.",
                "status": "success",
                "count": 50,
                "steps": steps,
                "method": "terraform" if use_terraform else "pymongo"
            })

        except Exception as e:
            return jsonify({"error": f"Generation failed: {str(e)}", "steps": steps}), 500

    @app.route("/")
    def index():
        """Serve the frontend."""
        return app.send_static_file("index.html")

    return app


# Run the app
if __name__ == "__main__":
    app = create_app()
    # Running without debug mode for stability in background
    app.run(host="0.0.0.0", port=5001)
