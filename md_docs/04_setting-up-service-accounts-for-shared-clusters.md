# How To: Setting Up Service Accounts for Shared Clusters

**Document ID**: KB-0004  
**Category**: How-To Guide  
**Domain**: Identity & Access Management  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Setting Up Service Accounts for Shared Clusters** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Atlas Project Admin privileges.
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
curl -X POST https://cloud.mongodb.com/api/atlas/v2/orgs/$ORG_ID/apiKeys -d '{"desc":"sa-kbase-ingest","roles":["GROUP_DATA_ACCESS_READ_WRITE"]}'
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
export MONGODB_SA_KEY='<generated_key>'
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
curl --digest -u "$ATLAS_PUBLIC_KEY:$ATLAS_PRIVATE_KEY" https://cloud.mongodb.com/api/atlas/v2/orgs/$ORG_ID/apiKeys
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `HTTP 403 Forbidden`

**Resolution**: Grant GROUP_DATA_ACCESS_ADMIN to project-level bindings.

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
