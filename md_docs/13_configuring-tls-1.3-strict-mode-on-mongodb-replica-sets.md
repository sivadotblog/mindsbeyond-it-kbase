# How To: Configuring TLS 1.3 Strict Mode on MongoDB Replica Sets

**Document ID**: KB-0013  
**Category**: How-To Guide  
**Domain**: Security & Encryption  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Configuring TLS 1.3 Strict Mode on MongoDB Replica Sets** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Root Access to Cluster Nodes, Internal CA Signed Certificates.
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
mongosh $MONGODB_URI --eval 'db.adminCommand({setParameter: 1, tlsWithServiceAccount: true, opensslCipherConfig: "TLS_AES_256_GCM_SHA384"})'
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
mongosh "mongodb://node1.mindsbeyond.com:27017" --tls --tlsCertificateKeyFile /etc/ssl/mongo.pem --tlsCAFile /etc/ssl/ca.pem
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
mongosh $MONGODB_URI --eval 'db.serverStatus().transportSecurity'
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `SSLHandshakeFailed`

**Resolution**: Confirm local CA file matches trusted internal enterprise root certificate.

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
