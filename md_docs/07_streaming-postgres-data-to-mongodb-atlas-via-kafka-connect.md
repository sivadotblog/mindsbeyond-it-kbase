# How To: Streaming Postgres Data to MongoDB Atlas via Kafka Connect

**Document ID**: KB-0007  
**Category**: How-To Guide  
**Domain**: Data Pipelines  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Streaming Postgres Data to MongoDB Atlas via Kafka Connect** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Kafka Cluster, Debezium Postgres Source Connector.
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
curl -X POST -H 'Content-Type: application/json' http://kafka-connect:8083/connectors -d '{"name":"pg-source","config":{"connector.class":"io.debezium.connector.postgresql.PostgresConnector","database.hostname":"pg.mindsbeyond.com","database.dbname":"kbase_db"}}'
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
curl -X POST -H 'Content-Type: application/json' http://kafka-connect:8083/connectors -d '{"name":"mongo-sink","config":{"connector.class":"com.mongodb.kafka.connect.MongoSinkConnector","connection.uri":"$MONGODB_URI"}}'
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
curl http://kafka-connect:8083/connectors/mongo-sink/status
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `ConnectException: Connection Refused`

**Resolution**: Check security group rules between Kafka Connect worker and Postgres.

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
