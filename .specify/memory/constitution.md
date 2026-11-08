# Mindsbeyond IT Knowledge Base Constitution

## Core Principles

### I. Atlas Does the AI Work

Embedding, vector retrieval, full-text retrieval, rank fusion and reranking run inside MongoDB Atlas
aggregation pipelines (`autoEmbed` indexes, `$vectorSearch`, `$search`, `$rankFusion`, `$scoreFusion`,
`$rerank`). The application does not call a separate embedding or rerank API for knowledge base
content. When a capability needs a newer server or a preview feature, the code names that
requirement in its error message instead of failing silently.

Rationale: the point of this repository is to demonstrate what Atlas can do on its own. Moving the AI
work into the app would hide the thing being demonstrated.

### II. Show the Work

Every search response returns the exact aggregation pipeline that ran, the timing, and the scores.
Every agent run returns an ordered trace of what the agent read, decided and did. Every memory read
returns the records it used and why they ranked where they did. The UI renders these, it does not
hide them.

Rationale: this is a demo and teaching tool. A result without its pipeline teaches nothing.

### III. Test First, Mock All I/O (NON-NEGOTIABLE)

Follow the Red, Green, Refactor cycle in `.cursorrules`. Unit tests use pytest and mock every external
dependency: MongoDB, HTTP, LLM providers, the file system where it matters. Unit tests never touch the
network. Tests that need a live Atlas cluster are marked `@pytest.mark.integration` and run only in
the manual live workflow. The coverage gate in `pyproject.toml` must stay green.

Rationale: the cluster, the models and the preview features change. Pure pipeline builders and mocked
services keep the suite fast and deterministic.

### IV. Credentials Stay Off the Agent

Agents never receive, echo, log or store secrets. SOP steps that need a credential or a privileged
action are human steps: the agent explains them and waits for a person to confirm. Secrets reach the
app only through environment variables. The repository is public, so nothing secret is committed.
In GitHub Actions the Atlas service account is `vars.MDB_CLIENT` (client id) and
`secrets.MDB_SECRET` (client secret). Database credentials made from it are short lived and deleted
after use.

Rationale: an SOP runner is useful only if it is safe to point at real procedures.

### V. Works Offline, Degrades Clearly

Every feature has an offline mode that needs no Atlas cluster and no LLM key, so the UI and tests run
anywhere. Offline results are labeled as offline in the API and the UI. When an optional backend
(Atlas, an LLM provider, Atlas Agent Engine memory) is missing or rejects a call, the API returns a
clear, typed error and the rest of the app keeps working.

Rationale: a demo that only works on one laptop with one set of keys is not a demo.

### VI. Keep It Simple

Plain HTML and vanilla JavaScript with no build step. Python 3.11+, Flask (already in use) and
PyMongo. Optional integrations (Anthropic, OpenAI compatible endpoints, Atlas Agent Engine memory)
are optional extras and are imported lazily. Pure functions build pipelines; thin services run them.
New dependencies need a reason written in the plan.

Rationale: the reader should be able to open one file and follow it.

## Technical Constraints

- Search features and their minimum server requirements are documented in the feature research and
  surfaced in the API capability report: `$vectorSearch` with `autoEmbed` (Atlas M10+, preview),
  `$rankFusion` (MongoDB 8.0+), `$scoreFusion` (MongoDB 8.3+), `$rerank` (Atlas with Native
  Reranking enabled, preview).
- The knowledge base collection and its existing indexes are preserved. New features add
  collections and indexes, they do not rename existing ones without a migration note.
- Existing API endpoints keep working. New endpoints live under `/api/v2/`.
- Documentation uses plain, simple sentences.

## Development Workflow

- Work follows the Spec Kit flow: constitution, specify, clarify, plan, tasks, analyze, implement.
  Each feature lives in `specs/NNN-short-name/`.
- Every pull request runs the unit test workflow. Live Atlas checks run from the manual
  `live-smoke` workflow.
- A pull request that changes a pipeline builder includes a test that asserts the pipeline shape.
- A pull request that adds an agent tool states whether the tool is read-only or changes state, and
  state-changing tools need a human confirmation step.

## Governance

This constitution overrides other practice documents in the repository when they conflict, except
`.cursorrules`, which it adopts for testing. Amendments happen by pull request that updates this
file, states the version bump and explains it. Versioning follows semantic versioning: MAJOR for
removing or redefining a principle, MINOR for adding a principle or section, PATCH for wording.
Reviewers check new plans against the Constitution Check gate in `plan.md`.

**Version**: 1.0.0 | **Ratified**: 2026-11-08 | **Last Amended**: 2026-11-08
