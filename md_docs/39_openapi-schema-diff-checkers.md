# How To: OpenAPI Schema Diff Checkers

**Document ID**: KB-0039  
**Category**: Tutorial  
**Domain**: API Governance  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **OpenAPI Schema Diff Checkers** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Enterprise Credentials for API Governance, Active Network Access.
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
openapi-diff old.json new.json --sourceID=SRC-99402 --env=prod
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
echo $? --config=/etc/mindsbeyond/config.json
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
echo 'Verifying OpenAPI Schema Diff Checkers...' && echo $?
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `Error: APIGovernanceExecutionFailed`

**Resolution**: Verify credentials and ensure target host is accessible via private endpoint.

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
