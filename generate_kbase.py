import os
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "kbase")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "content")
ATLAS_PUBLIC_KEY = os.getenv("ATLAS_PUBLIC_KEY")
ATLAS_PRIVATE_KEY = os.getenv("ATLAS_PRIVATE_KEY")
ATLAS_PROJECT_ID = os.getenv("ATLAS_PROJECT_ID")
ATLAS_CLUSTER_NAME = os.getenv("ATLAS_CLUSTER_NAME")

MD_DIR = "./md_docs"

# ------------------------------------------------------------------
# 1. Complete Catalog of 50 Unique Technical Topics
# ------------------------------------------------------------------
ARTICLES_DATA = [
    {
        "title": "Provisioning MongoDB Atlas Clusters with Terraform",
        "cat": "How-To Guide",
        "domain": "Infrastructure as Code",
        "prereq": "Terraform CLI 1.5+, Atlas Programmatic API Keys",
        "step1": "terraform init && terraform plan -var-file=mindsbeyond-prod.tfvars",
        "step2": "terraform apply -auto-approve -var-file=mindsbeyond-prod.tfvars",
        "verify": "az network private-endpoint show -g rg-mindsbeyond-data -n pe-atlas-eastus",
        "err": "Error 401 Unauthorized",
        "sol": "Verify ATLAS_PUBLIC_KEY and ATLAS_PRIVATE_KEY in environment variables."
    },
    {
        "title": "Configuring Azure Private Endpoints for MongoDB Atlas",
        "cat": "How-To Guide",
        "domain": "Networking & Security",
        "prereq": "Azure CLI, Contributor rights on VNet Subnet",
        "step1": "az network vnet subnet update -g rg-net --vnet-name vnet-mindsbeyond --name snet-db --disable-private-endpoint-network-policies true",
        "step2": "az network private-endpoint create -g rg-net -n pe-atlas-db --vnet-name vnet-mindsbeyond --subnet snet-db --private-connection-resource-id /subscriptions/sub-1/providers/MongoDB.Atlas",
        "verify": "nslookup -type=SRV _mongodb._tcp.kbase.private.mindsbeyond.com",
        "err": "MongoNetworkTimeoutError",
        "sol": "Ensure private DNS zone link is attached to the target VNet."
    },
    {
        "title": "Configuring Voyage AI Auto-Embeddings on Atlas Vector Search",
        "cat": "How-To Guide",
        "domain": "AI & Search",
        "prereq": "Atlas M10+ cluster, Voyage AI API Key registered",
        "step1": "curl -X POST https://cloud.mongodb.com/api/atlas/v2/groups/$ATLAS_PROJECT_ID/clusters/$CLUSTER/fts/indexes -H 'Content-Type: application/json' -d '{\"name\":\"vector_idx\",\"type\":\"vectorSearch\",\"definition\":{\"fields\":[{\"type\":\"autoEmbed\",\"path\":\"raw_markdown\",\"model\":\"voyage-context-4\",\"enable_auto_chunking\":true}]}}'",
        "step2": "mongosh $MONGODB_URI --eval 'db.content.getSearchIndexes()'",
        "verify": "mongosh $MONGODB_URI --eval 'db.content.aggregate([{\"$vectorSearch\": {\"index\": \"vector_idx\", \"path\": \"raw_markdown\", \"queryText\": \"private endpoint\", \"numCandidates\": 10, \"limit\": 1}}])'",
        "err": "IndexBuildFailed: Model voyage-context-4 unavailable",
        "sol": "Enable Voyage AI integration in Atlas Project Integrations UI."
    },
    {
        "title": "Setting Up Service Accounts for Shared Clusters",
        "cat": "How-To Guide",
        "domain": "Identity & Access Management",
        "prereq": "Atlas Project Admin privileges",
        "step1": "curl -X POST https://cloud.mongodb.com/api/atlas/v2/orgs/$ORG_ID/apiKeys -d '{\"desc\":\"sa-kbase-ingest\",\"roles\":[\"GROUP_DATA_ACCESS_READ_WRITE\"]}'",
        "step2": "export MONGODB_SA_KEY='<generated_key>'",
        "verify": "curl --digest -u \"$ATLAS_PUBLIC_KEY:$ATLAS_PRIVATE_KEY\" https://cloud.mongodb.com/api/atlas/v2/orgs/$ORG_ID/apiKeys",
        "err": "HTTP 403 Forbidden",
        "sol": "Grant GROUP_DATA_ACCESS_ADMIN to project-level bindings."
    },
    {
        "title": "Enforcing Cost Center Tags with Mindsbeyond SourceID",
        "cat": "How-To Guide",
        "domain": "FinOps & Billing",
        "prereq": "Access to Mindsbeyond Cloud Governance Portal",
        "step1": "az tag create --resource-id /subscriptions/sub-1/resourceGroups/rg-kbase --tags sourceID=SRC-99402 CostCenter=CC-8812",
        "step2": "python billing_audit.py --verify-tags --sourceID=SRC-99402",
        "verify": "curl -X GET https://billing.mindsbeyond.com/api/v1/verify?sourceID=SRC-99402",
        "err": "MissingTagException",
        "sol": "Pass sourceID explicitly in the request header or environment block."
    },
    {
        "title": "Building GitHub Actions Remote Dispatch Webhooks for KB Ingestion",
        "cat": "How-To Guide",
        "domain": "CI/CD & Automation",
        "prereq": "GitHub Repo Admin, Personal Access Token with repo scope",
        "step1": "curl -X POST -H 'Accept: application/vnd.github.v3+json' -H 'Authorization: token $GH_TOKEN' https://api.github.com/repos/mindsbeyond/kbase-docs/dispatches -d '{\"event_type\":\"doc_updated\",\"client_payload\":{\"doc_url\":\"https://raw.githubusercontent.com/.../doc.md\"}}'",
        "step2": "gh run list --repo mindsbeyond/kbase-docs --workflow=ingest.yml",
        "verify": "gh run view --repo mindsbeyond/kbase-docs --log",
        "err": "HTTP 422 Unprocessable Entity",
        "sol": "Verify event_type name matches the trigger in ingest.yml."
    },
    {
        "title": "Streaming Postgres Data to MongoDB Atlas via Kafka Connect",
        "cat": "How-To Guide",
        "domain": "Data Pipelines",
        "prereq": "Kafka Cluster, Debezium Postgres Source Connector",
        "step1": "curl -X POST -H 'Content-Type: application/json' http://kafka-connect:8083/connectors -d '{\"name\":\"pg-source\",\"config\":{\"connector.class\":\"io.debezium.connector.postgresql.PostgresConnector\",\"database.hostname\":\"pg.mindsbeyond.com\",\"database.dbname\":\"kbase_db\"}}'",
        "step2": "curl -X POST -H 'Content-Type: application/json' http://kafka-connect:8083/connectors -d '{\"name\":\"mongo-sink\",\"config\":{\"connector.class\":\"com.mongodb.kafka.connect.MongoSinkConnector\",\"connection.uri\":\"$MONGODB_URI\"}}'",
        "verify": "curl http://kafka-connect:8083/connectors/mongo-sink/status",
        "err": "ConnectException: Connection Refused",
        "sol": "Check security group rules between Kafka Connect worker and Postgres."
    },
    {
        "title": "Syncing Neo4j Knowledge Graphs to MongoDB Collections",
        "cat": "How-To Guide",
        "domain": "Graph Analytics",
        "prereq": "Neo4j Enterprise 5.x, APOC plugin enabled",
        "step1": "cypher-shell -u neo4j -p $NEO4J_PASS \"CALL apoc.mongodb.get('$MONGODB_URI', 'kbase', 'content', {}) YIELD value RETURN value;\"",
        "step2": "python neo4j_to_mongo_sync.py --batch-size=500 --collection=content",
        "verify": "mongosh $MONGODB_URI --eval 'db.content.countDocuments({graph_synced: true})'",
        "err": "Neo.ClientError.Procedure.ProcedureNotFound",
        "sol": "Install apoc-full plugin in /plugins directory of Neo4j node."
    },
    {
        "title": "Integrating Azure AI Foundry Models with Nexus Co-Pilot",
        "cat": "How-To Guide",
        "domain": "Enterprise AI",
        "prereq": "Azure AI Studio deployment, API Endpoint URL",
        "step1": "az ai service account create --name ai-nexus-foundry --resource-group rg-ai --kind AIStudio --location eastus2",
        "step2": "curl -X POST $AZURE_FOUNDRY_ENDPOINT/deployments/voyage-context-4/embeddings?api-version=2024-02-01 -H 'api-key: '$AZURE_AI_KEY -H 'Content-Type: application/json' -d '{\"input\":\"test search\"}'",
        "verify": "python test_nexus_copilot.py --endpoint=$AZURE_FOUNDRY_ENDPOINT",
        "err": "DeploymentNotFound",
        "sol": "Verify deployment name matches model name in Azure AI Studio."
    },
    {
        "title": "Configuring OpenAPI Specs for Internal API Gateways",
        "cat": "How-To Guide",
        "domain": "API Management",
        "prereq": "OpenAPI 3.0 specification in openapi.json format",
        "step1": "az apim api import -g rg-gateway -n apim-mindsbeyond --path /kbase-api --specification-format OpenApiJson --specification-path ./openapi.json",
        "step2": "curl -X GET https://gateway.mindsbeyond.com/kbase-api/v1/healthcheck -H 'Ocp-Apim-Subscription-Key: '$APIM_KEY",
        "verify": "az apim api show -g rg-gateway -n apim-mindsbeyond --api-id kbase-api",
        "err": "ValidationError: Missing Operation ID",
        "sol": "Ensure every endpoint path in openapi.json includes a unique operationId."
    },
    {
        "title": "Setting Up Databricks PySpark Drivers for Atlas JDBC Connections",
        "cat": "How-To Guide",
        "domain": "Data Engineering",
        "prereq": "Databricks Runtime 13.3 LTS, Mongo Spark Connector JAR",
        "step1": "databricks libraries install --cluster-id 0101-cluster --maven-coordinates com.mongodb.spark:mongo-spark-connector_2.12:10.2.0",
        "step2": "databricks runs submit --json '{\"run_name\":\"mongo_etl\",\"spark_jar_task\":{\"main_class_name\":\"com.mindsbeyond.MongoETL\"}}'",
        "verify": "databricks runs list --active-only",
        "err": "ClassNotFoundException: com.mongodb.spark.sql.DefaultSource",
        "sol": "Attach mongo-spark-connector library directly to target cluster."
    },
    {
        "title": "Querying Atlas Billing Dashboards via REST Management API",
        "cat": "How-To Guide",
        "domain": "FinOps",
        "prereq": "Atlas Org Read Only API Key",
        "step1": "curl --digest -u \"$ATLAS_PUBLIC_KEY:$ATLAS_PRIVATE_KEY\" -X GET https://cloud.mongodb.com/api/atlas/v2/orgs/$ORG_ID/invoices/pending",
        "step2": "python parse_billing.py --org-id=$ORG_ID --sourceID=SRC-99402",
        "verify": "ls -l ./billing_reports/monthly_chargeback.csv",
        "err": "HTTP 401 Unauthorized",
        "sol": "Ensure HTTP Digest authentication is enabled in curl or Python request client."
    },
    {
        "title": "Configuring TLS 1.3 Strict Mode on MongoDB Replica Sets",
        "cat": "How-To Guide",
        "domain": "Security & Encryption",
        "prereq": "Root Access to Cluster Nodes, Internal CA Signed Certificates",
        "step1": "mongosh $MONGODB_URI --eval 'db.adminCommand({setParameter: 1, tlsWithServiceAccount: true, opensslCipherConfig: \"TLS_AES_256_GCM_SHA384\"})'",
        "step2": "mongosh \"mongodb://node1.mindsbeyond.com:27017\" --tls --tlsCertificateKeyFile /etc/ssl/mongo.pem --tlsCAFile /etc/ssl/ca.pem",
        "verify": "mongosh $MONGODB_URI --eval 'db.serverStatus().transportSecurity'",
        "err": "SSLHandshakeFailed",
        "sol": "Confirm local CA file matches trusted internal enterprise root certificate."
    },
    {
        "title": "Setting Up Database-Level Authorization Rules in Atlas",
        "cat": "How-To Guide",
        "domain": "Access Control",
        "prereq": "Atlas Project Owner role",
        "step1": "curl -X POST https://cloud.mongodb.com/api/atlas/v2/groups/$ATLAS_PROJECT_ID/databaseUsers -d '{\"roles\":[{\"roleName\":\"readWrite\",\"databaseName\":\"kbase\"}],\"username\":\"app_nexus\",\"password\":\"$DB_PASS\"}'",
        "step2": "mongosh \"mongodb+srv://app_nexus:$DB_PASS@kbase.private.mindsbeyond.com/kbase\"",
        "verify": "mongosh $MONGODB_URI --eval 'db.getUser(\"app_nexus\")'",
        "err": "MongoServerError: Authentication Failed",
        "sol": "Check if database user was created under admin database namespace."
    },
    {
        "title": "Automating MDX Content Validation in GitHub Pipelines",
        "cat": "How-To Guide",
        "domain": "Developer Tooling",
        "prereq": "Node.js 18+, @mdx-js/mdx package",
        "step1": "npx mdx-bundler ./docs/*.mdx",
        "step2": "node ./scripts/validate_metadata.js --dir=./docs",
        "verify": "echo $?",
        "err": "SyntaxError: Unexpected JSX Element",
        "sol": "Ensure frontmatter headers conform strictly to YAML specs."
    },
    {
        "title": "Troubleshooting Private Endpoint Connection Timeouts",
        "cat": "How-To Guide",
        "domain": "Troubleshooting",
        "prereq": "Azure Network Watcher permissions",
        "step1": "az network watcher test-connectivity -g rg-net --source-resource vm-test --dest-address private-ep.kbase.mindsbeyond.com --dest-port 10260",
        "step2": "az network nsg rule list -g rg-net --nsg-name nsg-mindsbeyond-data --output table",
        "verify": "nc -zv private-ep.kbase.mindsbeyond.com 10260",
        "err": "Connection Refused (Port 10260)",
        "sol": "Add inbound rule allowing traffic on ports 10250-10270 to nsg-mindsbeyond-data."
    },
    {
        "title": "Configuring Log Forwarding from Atlas to Datadog",
        "cat": "How-To Guide",
        "domain": "Observability",
        "prereq": "Datadog API Key, Atlas Project Owner privileges",
        "step1": "curl -X POST https://cloud.mongodb.com/api/atlas/v2/groups/$ATLAS_PROJECT_ID/logIntegration -d '{\"type\":\"DATADOG\",\"apiKey\":\"$DD_KEY\",\"region\":\"US\"}'",
        "step2": "datadog-cli logs tail 'service:mongodb_atlas'",
        "verify": "curl -X GET https://cloud.mongodb.com/api/atlas/v2/groups/$ATLAS_PROJECT_ID/logIntegration",
        "err": "HTTP 400 Bad Request",
        "sol": "Verify Datadog region parameter matches your DD tenant region (US1 vs US5)."
    },
    {
        "title": "Setting Up Field-Level Encryption with Azure Key Vault",
        "cat": "How-To Guide",
        "domain": "Security & Compliance",
        "prereq": "Azure Key Vault, PyMongo Client with ClientEncryption plugin",
        "step1": "az keyvault key create --vault-name kv-mindsbeyond-sec --name mongo-master-key --kty RSA",
        "step2": "python create_enc_key.py --vault-url https://kv-mindsbeyond-sec.vault.azure.net/",
        "verify": "mongosh $MONGODB_URI --eval 'db.getCollectionInfos({name: \"content\"})'",
        "err": "KMSKeyProviderError",
        "sol": "Grant Azure Key Vault Crypto User role to the execution managed identity."
    },
    {
        "title": "Configuring TTL Indexes for Expiring Enterprise Logs",
        "cat": "How-To Guide",
        "domain": "Database Maintenance",
        "prereq": "MongoDB Admin Access on kbase database",
        "step1": "mongosh $MONGODB_URI --eval 'db.system_logs.createIndex({ \"createdAt\": 1 }, { expireAfterSeconds: 2592000 })'",
        "step2": "mongosh $MONGODB_URI --eval 'db.system_logs.getIndexes()'",
        "verify": "mongosh $MONGODB_URI --eval 'db.system_logs.stats().indexSizes'",
        "err": "IndexOptionsConflict",
        "sol": "Drop existing index on createdAt before creating TTL index with expireAfterSeconds."
    },
    {
        "title": "Scaling Atlas Cluster Tiers via Management API",
        "cat": "How-To Guide",
        "domain": "Capacity Planning",
        "prereq": "Atlas Project Owner API Keys",
        "step1": "curl -X PATCH https://cloud.mongodb.com/api/atlas/v2/groups/$ATLAS_PROJECT_ID/clusters/$CLUSTER -H 'Content-Type: application/json' -d '{\"providerSettings\":{\"instanceSizeName\":\"M30\"}}'",
        "step2": "curl https://cloud.mongodb.com/api/atlas/v2/groups/$ATLAS_PROJECT_ID/clusters/$CLUSTER",
        "verify": "mongosh $MONGODB_URI --eval 'db.hostInfo()'",
        "err": "CANNOT_DOWNGRADE_BELOW_STORAGE",
        "sol": "Ensure requested cluster tier supports the currently provisioned storage size."
    }
]

# Dynamically construct remaining 30 unique topics to reach 50
UNIQUE_MODULES = [
    ("Snowflake External Tables Setup", "Data Warehouse", "snowflake-cli", "SELECT * FROM mongo_ext_table"),
    ("Atlas Hybrid Search Querying", "AI & Search", "hybrid_search.py", "db.content.aggregate([{$search:...}])"),
    ("Data Platform Assistant CLI Setup", "Developer Tools", "dpa-cli init", "dpa-cli status"),
    ("Azure AD Single Sign-On Configuration", "Identity", "az ad app create", "az ad sso show"),
    ("OpenAPI Gateway Authentication Rules", "API Gateway", "apim policy apply", "curl -I https://api.mindsbeyond.com"),
    ("Zero-Downtime Migration Procedures", "Database Admin", "mongodump --oplog", "mongorestore --oplogReplay"),
    ("Custom Reranking with Voyage AI Reranker", "AI Search", "rerank_pipeline.py", "vo.rerank(query, docs)"),
    ("Network Peering Between Azure and Atlas", "Networking", "az network vnet peering create", "az network vnet peering show"),
    ("Nexus Copilot Custom Tool Plugins", "Enterprise AI", "nexus-plugin build", "nexus-plugin test"),
    ("Database Audit Logging to Azure Blob", "Compliance", "az storage blob upload", "az storage container list"),
    ("Atlas Search Synonym Ingestion", "Search Architecture", "import_synonyms.py", "db.content.aggregate([{$search:...}])"),
    ("Kafka Schema Registry Enforcement", "Event Streaming", "schema-registry-cli register", "schema-registry-cli check"),
    ("Private DNS Zone Linking for Atlas", "DNS Operations", "az network private-dns link create", "dig SRV mongo.mindsbeyond.com"),
    ("Multi-Region Replication Routing", "High Availability", "atlas cluster update --regions", "mongosh --host replSet/node1,node2"),
    ("Service Account Key Auto-Rotation", "Security Automation", "rotate_keys.py --sa=sa-kbase", "az keyvault secret show"),
    ("MongoDB Shell Scripting for Batch Updates", "DB Ops", "mongosh batch_update.js", "mongosh verify_update.js"),
    ("Azure Key Vault Managed Identity Setup", "Cloud IAM", "az identity create", "az identity show"),
    ("Atlas Storage Auto-Expansion Tuning", "Storage Ops", "atlas cluster storage enable-auto", "atlas cluster show"),
    ("OpenAPI Schema Diff Checkers", "API Governance", "openapi-diff old.json new.json", "echo $?"),
    ("End-to-End RAG Testing for KBase Agents", "AI Validation", "pytest test_rag_accuracy.py", "python eval_metrics.py"),
    ("Databricks Lakehouse Sink Configuration", "Lakehouse Ops", "spark-submit sink_job.py", "databricks runs get"),
    ("Graph Queries in Neo4j Agent Skills", "Graph Analytics", "cypher-shell MATCH (n) RETURN n", "python test_graph_agent.py"),
    ("Nexus RAG Knowledgebase Tooling", "Agent Frameworks", "nexus-agent register-tool", "nexus-agent test-tool"),
    ("Database Backup Validation Workflows", "Disaster Recovery", "atlas backups snapshots list", "atlas backups restore start"),
    ("Multi-Tenant Index Partitioning", "Index Tuning", "create_partition_idx.py", "db.content.getIndexes()"),
    ("Atlas Search Custom Analyzer Tuning", "Search Tuning", "apply_analyzer_config.py", "db.content.aggregate([{$search:...}])"),
    ("Data Platform Alert Webhooks Integration", "Alerting", "curl -X POST webhook.mindsbeyond.com", "curl -X GET webhook.mindsbeyond.com/status"),
    ("Atlas Memory Overhead Monitoring", "Performance", "mongosh --eval 'db.serverStatus().mem'", "mongosh --eval 'db.stats()'"),
    ("Migrating Legacy KBase Docs to Diátaxis", "Knowledge Mgmt", "python convert_to_diataxis.py", "pytest test_structure.py"),
    ("API Gateway Rate Limit Enforcement", "API Security", "apim policy rate-limit set", "curl -i https://api.mindsbeyond.com")
]

for i, (m_title, m_domain, m_cmd1, m_cmd2) in enumerate(UNIQUE_MODULES, start=21):
    ARTICLES_DATA.append({
        "title": m_title,
        "cat": "How-To Guide" if i % 2 == 0 else "Tutorial",
        "domain": m_domain,
        "prereq": f"Enterprise Credentials for {m_domain}, Active Network Access",
        "step1": f"{m_cmd1} --sourceID=SRC-99402 --env=prod",
        "step2": f"{m_cmd2} --config=/etc/mindsbeyond/config.json",
        "verify": f"echo 'Verifying {m_title}...' && {m_cmd2}",
        "err": f"Error: {m_domain.replace(' ', '')}ExecutionFailed",
        "sol": "Verify credentials and ensure target host is accessible via private endpoint."
    })


# ------------------------------------------------------------------
# 2. Generator Logic: Build 50 Unique Markdown Documents
# ------------------------------------------------------------------
def generate_markdown_files():
    """Generates 50 distinct Markdown files with unique technical content."""
    if not os.path.exists(MD_DIR):
        os.makedirs(MD_DIR)

    for idx, item in enumerate(ARTICLES_DATA, start=1):
        filename = f"{idx:02d}_{item['title'].lower().replace(' ', '-').replace('/', '-')}.md"
        filepath = os.path.join(MD_DIR, filename)

        md_content = f"""# How To: {item['title']}

**Document ID**: KB-{idx:04d}  
**Category**: {item['cat']}  
**Domain**: {item['domain']}  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **{item['title']}** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: {item['prereq']}.
2. **Environment Tags**: Set `MINDSBEYOND_SOURCE_ID="SRC-99402"` and `MINDSBEYOND_COST_CENTER="CC-8812"`.
3. **IAM Permissions**: Active Service Account permissions for database access and cloud infrastructure API calls.

---

## Step-by-Step Execution Guide

### Step 1: Environment Initialization & Context Setup
Configure billing tags and initialize the primary execution context in your shell environment:

```bash
# Set chargeback tracking variables
export MINDSBEYOND_SOURCE_ID="SRC-99402"
export MINDSBEYOND_COST_CENTER="CC-8812"

# Execute operational setup
{item['step1']}
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
{item['step2']}
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
{item['verify']}
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `{item['err']}`

**Resolution**: {item['sol']}

### Additional Support
- **Slack Channel**: #data-platform-support
- **ServiceNow Queue**: Data Platform Engineering
- **On-Call Escalation**: PagerDuty – Data Platform Team

---

## Related Documentation
- [MongoDB Atlas Administration Guide](https://docs.atlas.mongodb.com/)
- [Mindsbeyond Data Platform Wiki](https://wiki.mindsbeyond.com/data-platform)
- [Nexus Co-Pilot Documentation](https://nexus.mindsbeyond.com/docs)

---

*Last Updated*: Auto-generated  
*Maintainer*: Data Platform Engineering  
*Source ID*: SRC-99402  
"""

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"Generated: {filepath}")

    print(f"\n✅ Successfully generated {len(ARTICLES_DATA)} Markdown documents in '{MD_DIR}/'")


# ------------------------------------------------------------------
# 3. MongoDB Integration: Insert Documents into Atlas Collection
# ------------------------------------------------------------------
def insert_into_mongodb():
    """Inserts generated article metadata into MongoDB Atlas collection."""
    if not MONGODB_URI:
        print("❌ MONGODB_URI not set. Skipping MongoDB insertion.")
        return

    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    documents = []
    for idx, item in enumerate(ARTICLES_DATA, start=1):
        filename = f"{idx:02d}_{item['title'].lower().replace(' ', '-').replace('/', '-')}.md"
        filepath = os.path.join(MD_DIR, filename)
        
        # Read the generated markdown content
        raw_markdown = ""
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                raw_markdown = f.read()

        doc = {
            "doc_id": f"KB-{idx:04d}",
            "title": item["title"],
            "category": item["cat"],
            "domain": item["domain"],
            "prerequisites": item["prereq"],
            "steps": {
                "step1": item["step1"],
                "step2": item["step2"],
                "verify": item["verify"]
            },
            "troubleshooting": {
                "error": item["err"],
                "solution": item["sol"]
            },
            "metadata": {
                "source_id": "SRC-99402",
                "cost_center": "CC-8812",
                "framework": "Diataxis"
            },
            "raw_markdown": raw_markdown
        }
        documents.append(doc)

    # Upsert documents based on doc_id
    for doc in documents:
        collection.update_one(
            {"doc_id": doc["doc_id"]},
            {"$set": doc},
            upsert=True
        )
        print(f"Upserted: {doc['doc_id']} - {doc['title']}")

    print(f"\n✅ Successfully upserted {len(documents)} documents into {DB_NAME}.{COLLECTION_NAME}")
    client.close()


# ------------------------------------------------------------------
# 4. Main Entry Point
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("Mindsbeyond IT Knowledge Base Generator")
    print("=" * 60)
    
    # Step 1: Generate Markdown files
    print("\n📄 Generating Markdown documentation files...")
    generate_markdown_files()
    
    # Step 2: Insert into MongoDB Atlas
    print("\n🗄️  Inserting documents into MongoDB Atlas...")
    insert_into_mongodb()
    
    print("\n" + "=" * 60)
    print("Knowledge Base generation complete!")
    print("=" * 60)