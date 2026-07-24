# How To: Troubleshooting Private Endpoint Connection Timeouts

**Document ID**: KB-0016  
**Category**: How-To Guide  
**Domain**: Troubleshooting  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Troubleshooting Private Endpoint Connection Timeouts** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Azure Network Watcher permissions.
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
az network watcher test-connectivity -g rg-net --source-resource vm-test --dest-address private-ep.kbase.mindsbeyond.com --dest-port 10260
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
az network nsg rule list -g rg-net --nsg-name nsg-mindsbeyond-data --output table
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
nc -zv private-ep.kbase.mindsbeyond.com 10260
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `Connection Refused (Port 10260)`

**Resolution**: Add inbound rule allowing traffic on ports 10250-10270 to nsg-mindsbeyond-data.

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
