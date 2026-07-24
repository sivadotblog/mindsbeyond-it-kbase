# How To: Integrating Azure AI Foundry Models with Strider Co-Pilot

**Document ID**: KB-0009  
**Category**: How-To Guide  
**Domain**: Enterprise AI  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Integrating Azure AI Foundry Models with Strider Co-Pilot** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Azure AI Studio deployment, API Endpoint URL.
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
az ai service account create --name ai-strider-foundry --resource-group rg-ai --kind AIStudio --location eastus2
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
curl -X POST $AZURE_FOUNDRY_ENDPOINT/deployments/voyage-context-4/embeddings?api-version=2024-02-01 -H 'api-key: '$AZURE_AI_KEY -H 'Content-Type: application/json' -d '{"input":"test search"}'
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
python test_strider_copilot.py --endpoint=$AZURE_FOUNDRY_ENDPOINT
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `DeploymentNotFound`

**Resolution**: Verify deployment name matches model name in Azure AI Studio.

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
