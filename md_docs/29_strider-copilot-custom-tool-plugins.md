# How To: Strider Copilot Custom Tool Plugins

**Document ID**: KB-0029  
**Category**: Tutorial  
**Domain**: Enterprise AI  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Strider Copilot Custom Tool Plugins** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Enterprise Credentials for Enterprise AI, Active Network Access.
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
strider-plugin build --sourceID=SRC-99402 --env=prod
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
strider-plugin test --config=/etc/mindsbeyond/config.json
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
echo 'Verifying Strider Copilot Custom Tool Plugins...' && strider-plugin test
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `Error: EnterpriseAIExecutionFailed`

**Resolution**: Verify credentials and ensure target host is accessible via private endpoint.

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
