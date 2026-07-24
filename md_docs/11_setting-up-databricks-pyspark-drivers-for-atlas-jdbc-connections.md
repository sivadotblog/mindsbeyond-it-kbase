# How To: Setting Up Databricks PySpark Drivers for Atlas JDBC Connections

**Document ID**: KB-0011  
**Category**: How-To Guide  
**Domain**: Data Engineering  
**Framework**: Diátaxis Framework  

---

## Overview
This document outlines procedure steps for **Setting Up Databricks PySpark Drivers for Atlas JDBC Connections** in the internal Mindsbeyond Data Platform environment.

> ⚠️ **Network Prerequisite**: This procedure requires direct access through the Azure Private Endpoint. Connection attempts via standard public routing will be rejected.

---

## Prerequisites
Ensure the following operational prerequisites are satisfied before executing this workflow:
1. **Tooling & Access**: Databricks Runtime 13.3 LTS, Mongo Spark Connector JAR.
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
databricks libraries install --cluster-id 0101-cluster --maven-coordinates com.mongodb.spark:mongo-spark-connector_2.12:10.2.0
```

### Step 2: Primary Operation Execution
Execute the core operation workflow:

```bash
databricks runs submit --json '{"run_name":"mongo_etl","spark_jar_task":{"main_class_name":"com.mindsbeyond.MongoETL"}}'
```

---

## Verification & Validation

Confirm successful completion by running the following validation command:

```bash
databricks runs list --active-only
```

Expected outcome: Command completes without errors and returns expected resource state.

---

## Troubleshooting

### Common Error
**Error Message**: `ClassNotFoundException: com.mongodb.spark.sql.DefaultSource`

**Resolution**: Attach mongo-spark-connector library directly to target cluster.

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
