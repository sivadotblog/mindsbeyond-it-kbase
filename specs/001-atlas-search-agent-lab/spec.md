# Feature Specification: Atlas Search Lab, SOP Agent and Agent Memory

**Feature Branch**: `feat/atlas-search-lab-sop-agent-memory`

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: "Build on the existing setup. It indexes data in Atlas and serves it
through rerank and similar AI functions. Build a simple front end (HTML + JS), a Python backend to
demo Atlas vector searches using different search methods, an AI agent that uses the search to
perform a task such as an SOP, and an agent engine to demonstrate agent memory. Do deep research on
those topics. Use a spec driven approach (spec-kit). MDB_SECRET and MDB_CLIENT are a repo secret and
variable."

## Clarifications

### Session 2026-11-08

The request was made without a live session for questions, so these were answered with the most
reasonable reading. Each one can be changed by amending this spec.

- Q: Does "agent engine" mean MongoDB Atlas Agent Engine (public preview since 2026-09-29) or an
  agent runtime built in this repo? → A: Both. The repo ships a small agent engine (loop, tools,
  trace, memory hooks). Its memory layer is pluggable, with an Atlas backend built in this repo and
  an adapter for the Atlas Agent Engine memory service.
- Q: Which LLM does the agent use? → A: Provider neutral. The default is a deterministic offline
  planner so the demo runs with no key. Anthropic and any OpenAI compatible endpoint (for example
  Azure AI Foundry) can be turned on by configuration.
- Q: What are `MDB_CLIENT` and `MDB_SECRET` for? → A: They are an Atlas service account (client id
  as a repo variable, client secret as a repo secret). A service account reaches the Atlas
  Administration API, not cluster data. GitHub Actions uses it to grant short lived database access
  for live checks and to mint Agent Engine tokens when that backend is enabled.
- Q: Which search methods should the demo cover? → A: Full text, vector ANN, vector ENN, filtered
  vector, hybrid by rank fusion, hybrid by score fusion, and an optional rerank pass on any of them,
  plus a choice of query embedding model within the voyage-4 family.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compare search methods side by side (Priority: P1)

A platform engineer types a question such as "private endpoint connection timeout" into the Search
Lab, picks the methods to compare, and sees one ranked column per method. Each column shows the
articles, scores, latency and the exact pipeline that ran. A summary shows where the methods agree
and where they differ, and what reranking changed.

**Why this priority**: This is the core of the request and it works on its own. It shows the value of
each Atlas retrieval feature on the existing data with no agent involved.

**Independent Test**: Load the knowledge base, open the Search Lab, run one query across all
methods, and confirm every column returns results with a pipeline and timing, or a clear reason why
the method is not available.

**Acceptance Scenarios**:

1. **Given** the knowledge base is loaded and indexed, **When** the engineer runs a query with
   full text, vector and hybrid selected, **Then** each method returns up to the requested number of
   articles with scores, latency and its pipeline.
2. **Given** results are shown, **When** the engineer turns on rerank, **Then** each column shows the
   reranked order and how far each article moved compared to the order before reranking.
3. **Given** a method needs a feature the cluster lacks, **When** the engineer runs it, **Then**
   that column shows the requirement (for example "needs MongoDB 8.3+") and the other columns still
   return results.
4. **Given** the engineer sets a category or domain filter, **When** they run filtered vector
   search, **Then** every result matches the filter.
5. **Given** no cluster is configured, **When** the engineer opens the lab, **Then** the lab runs in
   offline mode on the local markdown files and labels every result as offline.

---

### User Story 2 - Run an SOP with an agent (Priority: P2)

An engineer describes a task in plain words, for example "rotate the kbase ingest service account
key". The agent searches the knowledge base, picks the best matching procedure and says why, then
turns it into a checklist: prerequisites, steps, verification and troubleshooting. The agent does
the steps it can do safely itself (look up related articles, explain a command, check that a
prerequisite is documented). Steps that run commands, need credentials or change systems are
marked as human steps and wait for the engineer to confirm done, failed or skipped. When a step
fails, the agent pulls the troubleshooting section and related articles. At the end it writes a
short run summary.

**Why this priority**: It turns retrieval into an outcome. It depends on search (P1) but not on
long term memory.

**Independent Test**: Start a run for a task that matches a known article, walk the checklist to the
end, and confirm the trace shows the search, the chosen SOP, each step and the summary.

**Acceptance Scenarios**:

1. **Given** a task description, **When** the engineer starts a run, **Then** the agent shows the
   top candidate procedures with scores and the one it chose with a reason.
2. **Given** a chosen procedure, **When** the run starts, **Then** the checklist lists every
   prerequisite, step, verification command and the known error with its fix, each tagged as agent
   or human.
3. **Given** a human step, **When** the engineer marks it failed with a note, **Then** the agent
   adds troubleshooting guidance from the procedure and from related articles before moving on.
4. **Given** any run, **When** the engineer opens the trace, **Then** every search, decision, tool
   call and confirmation appears in order with timing.
5. **Given** any run, **When** the agent handles a step, **Then** it never asks for, shows or stores
   a secret value.

---

### User Story 3 - The agent remembers across runs (Priority: P3)

An engineer finishes an SOP run in which they said "our cluster is kbase-prod" and noted "step 2
needed port 10260 open". Next week they start a similar task. The agent recalls the cluster name,
the note about the port and a summary of the earlier run, and shows which memories it used and why
they ranked high. A Memory Explorer lists memories by type (short term, episodic, semantic,
procedural, taxonomic), lets the engineer search memory and see the relevance, recency and
importance parts of each score, and lets them delete a memory.

**Why this priority**: Memory is what makes the agent improve with use, but the lab and the SOP
runner already deliver value without it.

**Independent Test**: Run an SOP, state a fact and a step note, finish the run, start a second
related run, and confirm the agent shows the recalled fact, note and episode in its plan.

**Acceptance Scenarios**:

1. **Given** a finished run, **When** the engineer opens the Memory Explorer, **Then** it shows an
   episode for the run, any stated facts as semantic memories and step notes as procedural
   memories, all scoped to that user.
2. **Given** stored memories, **When** a new run starts for a related task, **Then** the agent's plan
   includes the recalled memories with their scores and the reason each was used.
3. **Given** a fact is stated again with new content (for example a new cluster name), **When**
   memory is consolidated, **Then** the old fact is updated rather than duplicated.
4. **Given** a memory the engineer wants gone, **When** they delete it, **Then** later runs no
   longer recall it.
5. **Given** the Atlas Agent Engine memory service is configured, **When** the engineer switches the
   memory backend, **Then** the same flows work against that service and the explorer shows which
   backend is active.

---

### User Story 4 - Verify against live Atlas from GitHub Actions (Priority: P4)

A maintainer runs a manual GitHub Actions workflow. It uses the Atlas service account stored as
`MDB_CLIENT` and `MDB_SECRET` to grant a temporary database user and a temporary network access
entry, seeds the knowledge base, builds the indexes, runs a smoke check of every search method and
the agent, prints a capability report, and removes the temporary access even when a step fails.

**Why this priority**: It proves the demo against the real cluster without anyone pasting
credentials, but the features above work without it.

**Independent Test**: Trigger the workflow and confirm the job summary lists each method with pass,
fail or not supported, and that the temporary user and access entry are gone afterwards.

**Acceptance Scenarios**:

1. **Given** the variable and secret are set, **When** the workflow runs, **Then** it finds the
   project and cluster, grants access that expires within a few hours, and deletes it in a final
   step that runs even after failures.
2. **Given** a search method is not supported by the cluster, **When** the smoke check runs, **Then**
   it is reported as not supported, not as a crash.

### Edge Cases

- Empty or whitespace query: rejected with a clear message.
- Very long query (over 1,000 characters): rejected or trimmed with a message.
- Requested limit outside 1 to 50: clamped.
- Search indexes still building: the method reports "index not ready" instead of an empty list.
- Reranker returns a constant score because Native Reranking is not enabled: the lab flags it.
- Task that matches no procedure well: the agent says so, shows the closest candidates and does not
  start a checklist.
- Run abandoned half way: it stays resumable and is summarized as incomplete.
- Memory backend unreachable: the agent runs without long term memory and says so in the trace.
- Two users: one user's private memories never appear in the other user's runs.
- Workflow cancelled mid run: the temporary access still expires on its own.

## Requirements *(mandatory)*

### Functional Requirements

**Search Lab**

- **FR-001**: System MUST offer these methods: full text, vector ANN, vector ENN, filtered vector,
  hybrid rank fusion, hybrid score fusion.
- **FR-002**: System MUST let any method be followed by an optional rerank pass, and MUST report the
  rank change of each result caused by reranking.
- **FR-003**: System MUST return, for every method, the ranked results, each score, the latency and
  the exact pipeline that ran.
- **FR-004**: System MUST let the user choose the query embedding model from the models compatible
  with the index, the number of results, the candidate pool size, fusion weights and filters.
- **FR-005**: System MUST run several methods for one query in one request and return an agreement
  summary (overlap of result sets and rank differences).
- **FR-006**: System MUST report cluster capabilities (server version, index status and which
  methods are available) and use them to explain unavailable methods.
- **FR-007**: System MUST keep the existing endpoints working and fix the existing hybrid search so
  it targets the full text index that is actually created.

**SOP Agent**

- **FR-008**: System MUST find candidate procedures for a free text task using the knowledge base
  search, and MUST show the candidates and the reason for the choice.
- **FR-009**: System MUST turn a procedure into an ordered checklist of prerequisites, steps,
  verification and troubleshooting, each tagged agent step or human step.
- **FR-010**: System MUST treat any step that runs a command, needs a credential or changes a system
  as a human step that needs explicit confirmation (done, failed, skipped) with an optional note.
- **FR-011**: System MUST, when a step fails, attach the procedure's troubleshooting guidance and
  related articles.
- **FR-012**: System MUST record an ordered trace of every search, decision, tool call and
  confirmation with timestamps, and return it with the run.
- **FR-013**: System MUST keep runs so they can be resumed and reviewed, and MUST produce a summary
  when a run ends or is abandoned.
- **FR-014**: System MUST never request, display or persist secret values, and MUST redact strings
  that look like secrets from notes before storing them.
- **FR-015**: System MUST work with no LLM configured, and MUST use a configured LLM to pick the
  procedure, explain steps and extract facts when one is available.

**Agent Memory**

- **FR-016**: System MUST store memory in five types: short term (turns of the current run),
  episodic (summaries of past runs), semantic (labeled facts), procedural (how-to notes tied to a
  procedure) and taxonomic (domain terms).
- **FR-017**: System MUST scope every memory to a user and optionally an agent, with private or
  shared visibility, and MUST never return another user's private memory.
- **FR-018**: System MUST retrieve memory with a score that combines relevance, recency and
  importance, and MUST return each part of the score.
- **FR-019**: System MUST consolidate new facts against existing ones: add new, update changed,
  ignore duplicates.
- **FR-020**: System MUST expire short term memory automatically after a set time.
- **FR-021**: System MUST let a user list, search and delete memories.
- **FR-022**: System MUST support three memory backends behind one interface: Atlas collections
  built by this repo, the Atlas Agent Engine memory service, and an in process store for offline
  use and tests.

**Live verification**

- **FR-023**: System MUST provide a manual workflow that uses the Atlas service account to create a
  short lived database user and network access entry, run the smoke checks, and delete both in an
  always run cleanup step.
- **FR-024**: System MUST produce a capability and smoke report that marks each method pass, fail or
  not supported.

### Key Entities

- **Article**: a knowledge base document (id, title, category, domain, prerequisites, steps,
  verification, troubleshooting, markdown body).
- **Search Method**: a named way to retrieve articles, with its parameters and requirements.
- **Search Run**: one query across one or more methods, with results, scores, timing and pipelines.
- **Capability Report**: what the connected cluster supports and why a method is unavailable.
- **SOP Run**: one agent run of one procedure for one user: task, candidates, chosen procedure,
  checklist, status, trace and summary.
- **Checklist Step**: one item in a run: kind (prerequisite, step, verify, troubleshoot), actor
  (agent or human), status, note, guidance.
- **Trace Event**: one ordered record of something the agent read, decided or did.
- **Memory Record**: one stored memory: type, content, label or title, user, agent, visibility,
  importance, timestamps, source run, and its score parts when retrieved.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An engineer can compare all six search methods for one query in a single action and
  read the results, scores and pipelines in under one minute.
- **SC-002**: For the 50 article knowledge base, a single method returns in under 2 seconds and a
  six method comparison in under 5 seconds on an M10 class cluster, excluding first index build.
- **SC-003**: For 10 sample tasks written from article titles in different words, the agent picks
  the intended procedure as its first choice at least 8 times.
- **SC-004**: An engineer can finish a run of a known procedure, including human confirmations, in
  under 5 minutes.
- **SC-005**: In a second related run, every fact and step note stated in the first run is recalled
  in the plan (recall of 100% on the scripted demo).
- **SC-006**: Zero secret values appear in traces, memory or logs in the automated tests that feed
  secret like strings into notes.
- **SC-007**: With no cluster and no LLM key, the whole UI loads and every flow runs in offline
  mode.
- **SC-008**: The live workflow leaves no temporary database user or access entry behind, in both
  passing and failing runs.

## Assumptions

- Users are platform engineers who know the procedures in the knowledge base. The UI is a demo, not
  a hardened product, so there is no login; the user id is chosen in the UI.
- The Atlas cluster is M10 or larger, already has the knowledge base loaded by the existing Admin
  tab, and the existing autoEmbed index uses a voyage-4 family model.
- Preview features (automated embedding, native reranking, Agent Engine) can change. The code keeps
  their request shapes in one place so a change is a one file fix.
- Agent steps never execute shell commands. "Doing" a step means looking up, explaining and
  checking, not running.
- Mobile layout only needs to be readable, not optimized.
- Out of scope: user authentication, multi tenant deployment, executing commands from SOPs,
  streaming LLM tokens, and the Atlas Search lexical prefilter (`$search.vectorSearch`), which needs
  a different index type than the existing autoEmbed index.
