# How To: Enforcing Cost Center Tags with Mindsbeyond SourceID

**Document ID**: KB-0005  
**Category**: How-To Guide  
**Domain**: FinOps & Billing  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Enforcing Cost Center Tags with Mindsbeyond SourceID** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Access to Mindsbeyond Cloud Governance Portal.
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
az tag create --resource-id /subscriptions/sub-1/resourceGroups/rg-kbase --tags sourceID=SRC-99402 CostCenter=CC-8812
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
python billing_audit.py --verify-tags --sourceID=SRC-99402
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
curl -X GET https://billing.mindsbeyond.com/api/v1/verify?sourceID=SRC-99402
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `MissingTagException`

**Resolution**: Pass sourceID explicitly in the request header or environment block.

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
