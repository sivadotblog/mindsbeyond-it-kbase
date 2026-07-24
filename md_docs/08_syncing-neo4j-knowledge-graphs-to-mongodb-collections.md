# How To: Syncing Neo4j Knowledge Graphs to MongoDB Collections

**Document ID**: KB-0008  
**Category**: How-To Guide  
**Domain**: Graph Analytics  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Syncing Neo4j Knowledge Graphs to MongoDB Collections** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Neo4j Enterprise 5.x, APOC plugin enabled.
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
cypher-shell -u neo4j -p $NEO4J_PASS "CALL apoc.mongodb.get('$MONGODB_URI', 'kbase', 'content', {}) YIELD value RETURN value;"
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
python neo4j_to_mongo_sync.py --batch-size=500 --collection=content
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
mongosh $MONGODB_URI --eval 'db.content.countDocuments({graph_synced: true})'
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `Neo.ClientError.Procedure.ProcedureNotFound`

**Resolution**: Install apoc-full plugin in /plugins directory of Neo4j node.

### Additional Support
- **Slack Channel**: #data-platform-support
- **ServiceNow Queue**: Data Platform Engineering
- **On-Call Escalation**: PagerDuty – Data Platform Team

---

## Related Documentation
- [MongoDB Atlas Administration Guide](https://docs.atlas.mongodb.com/)
- [Mindsbeyond Data Platform Wiki](https://wiki.mindsbeyond.com/data-platform)
- [Strider Co-Pilot Documentation](https://strider.mindsbeyond.com/docs)

---

*Last Updated*: Auto-generated  
*Maintainer*: Data Platform Engineering  
*Source ID*: SRC-99402  
