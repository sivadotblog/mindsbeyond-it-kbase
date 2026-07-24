# How To: Configuring OpenAPI Specs for Internal API Gateways

**Document ID**: KB-0010  
**Category**: How-To Guide  
**Domain**: API Management  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Configuring OpenAPI Specs for Internal API Gateways** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: OpenAPI 3.0 specification in openapi.json format.
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
az apim api import -g rg-gateway -n apim-mindsbeyond --path /kbase-api --specification-format OpenApiJson --specification-path ./openapi.json
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
curl -X GET https://gateway.mindsbeyond.com/kbase-api/v1/healthcheck -H 'Ocp-Apim-Subscription-Key: '$APIM_KEY
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
az apim api show -g rg-gateway -n apim-mindsbeyond --api-id kbase-api
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `ValidationError: Missing Operation ID`

**Resolution**: Ensure every endpoint path in openapi.json includes a unique operationId.

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
