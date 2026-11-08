---

description: "Task list for the Atlas Search Lab, SOP Agent and Agent Memory feature"
---

# Tasks: Atlas Search Lab, SOP Agent and Agent Memory

**Input**: Design documents from `/specs/001-atlas-search-agent-lab/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml

**Tests**: Required. The constitution (III) makes tests first with mocked I/O non negotiable.

**Organization**: Grouped by user story so each story can ship and be tested on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 to US4 from spec.md

## Phase 1: Setup

- [x] T001 Initialize Spec Kit for Claude (`.specify/`, `.claude/skills/speckit-*`)
- [ ] T002 Add packaging and dependencies in `pyproject.toml` (Python 3.11+, Flask, PyMongo, requests,
      extras `dev` and `agent-engine`, setuptools package discovery for `kbase`)
- [ ] T003 [P] Add `.gitignore` entries for `.atlas-access.json` and `smoke-report.md`

## Phase 2: Foundational

- [ ] T004 Settings from environment in `kbase/config.py` with tests in `tests/test_config.py`
- [ ] T005 [P] Secret redaction in `kbase/redact.py` with tests in `tests/test_redact.py`
- [ ] T006 [P] Markdown article parser in `kbase/search/docs.py` (shared by offline search and SOP
      parsing) with tests in `tests/test_search_offline.py`
- [ ] T007 Service container and `/api/v2/health` in `kbase/container.py` and `kbase/api.py`,
      registered from `app.py`

**Checkpoint**: app starts in offline and Atlas mode; health reports mode, LLM and memory backends.

## Phase 3: User Story 1 - Compare search methods (P1) MVP

### Tests for US1

- [ ] T008 [P] [US1] Pipeline shape tests for every method, filters, fusion options and rerank tail
      in `tests/test_search_pipelines.py`
- [ ] T009 [P] [US1] Agreement metric tests in `tests/test_compare.py`
- [ ] T010 [P] [US1] SearchService tests (run, compare, rank deltas, unsupported mapping, query
      shape fallback, constant rerank warning, capabilities) in `tests/test_search_service.py`
- [ ] T011 [P] [US1] Offline search tests (BM25, TF-IDF, RRF, score fusion) in
      `tests/test_search_offline.py`
- [ ] T012 [P] [US1] v2 search endpoint tests in `tests/test_api_v2.py`

### Implementation for US1

- [ ] T013 [US1] Pure builders in `kbase/search/pipelines.py`
- [ ] T014 [US1] Method registry in `kbase/search/methods.py`
- [ ] T015 [US1] Agreement metrics in `kbase/search/compare.py`
- [ ] T016 [US1] `SearchService` with capability probe in `kbase/search/service.py`
- [ ] T017 [US1] `OfflineSearchService` in `kbase/search/offline.py`
- [ ] T018 [US1] Endpoints `/api/v2/capabilities`, `/search/methods`, `/search`, `/search/compare`
- [ ] T019 [US1] Fix v1 hybrid search text index name in `app.py` (FR-007)
- [ ] T020 [US1] Search Lab tab in `static/lab.html`, `static/lab.js`, `static/lab.css`

**Checkpoint**: Search Lab works offline and on Atlas.

## Phase 4: User Story 2 - Run an SOP with an agent (P2)

### Tests for US2

- [ ] T021 [P] [US2] LLM port tests (offline, anthropic, openai, JSON parsing, fallback) in
      `tests/test_llm.py`
- [ ] T022 [P] [US2] Checklist builder tests (actor tagging, hints, secret variables never filled)
      in `tests/test_sop.py`
- [ ] T023 [P] [US2] Trace and engine tests in `tests/test_engine.py`
- [ ] T024 [P] [US2] Run store tests in `tests/test_runs.py`
- [ ] T025 [P] [US2] SOP agent tests (choose, no match, confirm, failure guidance, messages,
      finish, redaction) in `tests/test_sop_agent.py`

### Implementation for US2

- [ ] T026 [US2] `kbase/agent/llm.py`
- [ ] T027 [US2] `kbase/agent/trace.py` and `kbase/agent/engine.py`
- [ ] T028 [US2] `kbase/agent/sop.py`
- [ ] T029 [US2] `kbase/agent/runs.py`
- [ ] T030 [US2] `kbase/agent/sop_agent.py`
- [ ] T031 [US2] Agent endpoints in `kbase/api.py`
- [ ] T032 [US2] SOP Agent tab in the lab UI

**Checkpoint**: an SOP run can be completed end to end without memory.

## Phase 5: User Story 3 - Agent memory (P3)

### Tests for US3

- [ ] T033 [P] [US3] Scoring tests in `tests/test_memory_scoring.py`
- [ ] T034 [P] [US3] In process store tests (scoping, TTL, delete) in `tests/test_memory_inmemory.py`
- [ ] T035 [P] [US3] Extraction and consolidation tests in `tests/test_memory_consolidate.py`
- [ ] T036 [P] [US3] Atlas store tests (index definitions, recall pipeline shape, visibility filter,
      writes) in `tests/test_memory_atlas.py`
- [ ] T037 [P] [US3] Agent Engine adapter tests with a fake SDK in `tests/test_memory_agent_engine.py`

### Implementation for US3

- [ ] T038 [US3] `kbase/memory/models.py`, `scoring.py`, `base.py`
- [ ] T039 [US3] `kbase/memory/inmemory.py`
- [ ] T040 [US3] `kbase/memory/extract.py` and `consolidate.py`
- [ ] T041 [US3] `kbase/memory/atlas.py`
- [ ] T042 [US3] `kbase/memory/agent_engine.py`
- [ ] T043 [US3] Memory hooks in the engine and SOP agent (recall on start, STM on messages,
      episode, facts and notes on finish)
- [ ] T044 [US3] Memory endpoints in `kbase/api.py`
- [ ] T045 [US3] Memory Explorer tab in the lab UI

**Checkpoint**: the scripted demo in quickstart.md recalls the fact, the note and the episode.

## Phase 6: User Story 4 - Live verification (P4)

- [ ] T046 [P] [US4] Admin API client tests (token, discovery, grant, revoke, outputs, masking) in
      `tests/test_atlas_admin.py`
- [ ] T047 [P] [US4] Smoke report tests in `tests/test_smoke.py`
- [ ] T048 [US4] `kbase/atlas_admin.py` with CLI `grant` and `revoke`
- [ ] T049 [US4] `kbase/smoke.py` with CLI `setup` and `run`
- [ ] T050 [US4] `.github/workflows/live-smoke.yml` (manual, always run cleanup)

## Phase 7: Polish

- [ ] T051 [P] `.github/workflows/ci.yml` (unit tests and coverage gate on push and pull request)
- [ ] T052 [P] README section for the lab, the agent, memory and the workflows
- [ ] T053 Link the lab from `static/index.html`
- [ ] T054 Run the full suite and the coverage gate
- [ ] T055 Load the lab offline in a browser and check each tab
- [ ] T056 Cross artifact consistency check (speckit-analyze) and record findings

## Dependencies

- Phase 2 blocks all stories.
- US1 has no story dependency. US2 uses the search service from US1. US3 plugs into the engine
  from US2 but its store and explorer can be built in parallel. US4 depends on US1 to US3 for what
  it checks.
- Inside each story: tests first, then models, then services, then endpoints, then UI.

## Parallel examples

- T008 to T012 can be written together.
- T033 to T037 can be written together.
- T046 and T047 can be written together.
