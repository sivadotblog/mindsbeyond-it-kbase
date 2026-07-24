# How To: Querying Atlas Billing Dashboards via REST Management API

**Document ID**: KB-0012  
**Category**: How-To Guide  
**Domain**: FinOps  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Querying Atlas Billing Dashboards via REST Management API** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Atlas Org Read Only API Key.
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
curl --digest -u "$ATLAS_PUBLIC_KEY:$ATLAS_PRIVATE_KEY" -X GET https://cloud.mongodb.com/api/atlas/v2/orgs/$ORG_ID/invoices/pending
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
python parse_billing.py --org-id=$ORG_ID --sourceID=SRC-99402
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
ls -l ./billing_reports/monthly_chargeback.csv
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `HTTP 401 Unauthorized`

**Resolution**: Ensure HTTP Digest authentication is enabled in curl or Python request client.

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
