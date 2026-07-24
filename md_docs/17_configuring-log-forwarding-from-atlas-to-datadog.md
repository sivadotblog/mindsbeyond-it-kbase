# How To: Configuring Log Forwarding from Atlas to Datadog

**Document ID**: KB-0017  
**Category**: How-To Guide  
**Domain**: Observability  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Configuring Log Forwarding from Atlas to Datadog** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Datadog API Key, Atlas Project Owner privileges.
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
curl -X POST https://cloud.mongodb.com/api/atlas/v2/groups/$ATLAS_PROJECT_ID/logIntegration -d '{"type":"DATADOG","apiKey":"$DD_KEY","region":"US"}'
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
datadog-cli logs tail 'service:mongodb_atlas'
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
curl -X GET https://cloud.mongodb.com/api/atlas/v2/groups/$ATLAS_PROJECT_ID/logIntegration
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `HTTP 400 Bad Request`

**Resolution**: Verify Datadog region parameter matches your DD tenant region (US1 vs US5).

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
