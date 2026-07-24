# How To: Setting Up Field-Level Encryption with Azure Key Vault

**Document ID**: KB-0018  
**Category**: How-To Guide  
**Domain**: Security & Compliance  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Setting Up Field-Level Encryption with Azure Key Vault** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Azure Key Vault, PyMongo Client with ClientEncryption plugin.
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
az keyvault key create --vault-name kv-mindsbeyond-sec --name mongo-master-key --kty RSA
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
python create_enc_key.py --vault-url https://kv-mindsbeyond-sec.vault.azure.net/
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
mongosh $MONGODB_URI --eval 'db.getCollectionInfos({name: "content"})'
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `KMSKeyProviderError`

**Resolution**: Grant Azure Key Vault Crypto User role to the execution managed identity.

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
