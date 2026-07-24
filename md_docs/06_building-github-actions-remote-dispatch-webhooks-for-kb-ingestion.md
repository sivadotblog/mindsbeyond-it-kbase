# How To: Building GitHub Actions Remote Dispatch Webhooks for KB Ingestion

**Document ID**: KB-0006  
**Category**: How-To Guide  
**Domain**: CI/CD & Automation  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Building GitHub Actions Remote Dispatch Webhooks for KB Ingestion** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: GitHub Repo Admin, Personal Access Token with repo scope.
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
curl -X POST -H 'Accept: application/vnd.github.v3+json' -H 'Authorization: token $GH_TOKEN' https://api.github.com/repos/mindsbeyond/kbase-docs/dispatches -d '{"event_type":"doc_updated","client_payload":{"doc_url":"https://raw.githubusercontent.com/.../doc.md"}}'
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
gh run list --repo mindsbeyond/kbase-docs --workflow=ingest.yml
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
gh run view --repo mindsbeyond/kbase-docs --log
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `HTTP 422 Unprocessable Entity`

**Resolution**: Verify event_type name matches the trigger in ingest.yml.

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
