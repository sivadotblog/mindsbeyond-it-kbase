# How To: Configuring Voyage AI Auto-Embeddings on Atlas Vector Search

**Document ID**: KB-0003  
**Category**: How-To Guide  
**Domain**: AI & Search  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Configuring Voyage AI Auto-Embeddings on Atlas Vector Search** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Atlas M10+ cluster, Voyage AI API Key registered.
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
curl -X POST https://cloud.mongodb.com/api/atlas/v2/groups/$ATLAS_PROJECT_ID/clusters/$CLUSTER/fts/indexes -H 'Content-Type: application/json' -d '{"name":"vector_idx","type":"vectorSearch","definition":{"fields":[{"type":"autoEmbed","path":"raw_markdown","model":"voyage-context-4","enable_auto_chunking":true}]}}'
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
mongosh $MONGODB_URI --eval 'db.content.getSearchIndexes()'
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
mongosh $MONGODB_URI --eval 'db.content.aggregate([{"$vectorSearch": {"index": "vector_idx", "path": "raw_markdown", "queryText": "private endpoint", "numCandidates": 10, "limit": 1}}])'
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `IndexBuildFailed: Model voyage-context-4 unavailable`

**Resolution**: Enable Voyage AI integration in Atlas Project Integrations UI.

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
