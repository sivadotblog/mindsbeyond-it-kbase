# Working in this repo

- Read `.specify/memory/constitution.md` first. Tests first with mocked I/O, pipelines returned
  with every result, no secrets near the agent, offline mode must keep working.
- Feature specs live in `specs/NNN-name/` and follow Spec Kit (`/speckit-specify`, `/speckit-plan`,
  `/speckit-tasks`, `/speckit-implement`). The current feature is `specs/001-atlas-search-agent-lab/`.
- Testing rules are in `.cursorrules` (pytest, factory functions, one focus per test).
- Run tests: `pip install -e ".[dev]"` then `pytest --cov`.
- Run the app offline: `KBASE_MODE=offline python app.py`, then open http://localhost:5001/lab.html.
- Atlas request shapes for preview features (autoEmbed query, `$rerank`, `$scoreFusion`) live only in
  `kbase/search/pipelines.py` and `kbase/memory/atlas.py`. Change them there.
- Agent tools must be read only. Anything that changes a system is a human step in the checklist.
