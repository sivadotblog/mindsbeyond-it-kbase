"""Tests for the checklist builder."""
from kbase.agent.sop import build_checklist, failure_guidance, match_confidence, memory_hints
from kbase.memory.models import MemoryHit, MemoryRecord


def hit(**kw):
    base = {"type": "semantic", "user_id": "u1", "content": "cluster = kbase-prod", "label": "cluster"}
    base.update(kw)
    return MemoryHit(record=MemoryRecord(**base), score=0.5, relevance=0.5, recency=1, importance=0.5)


def article(**kw):
    base = {
        "doc_id": "KB-0020", "title": "Scaling Atlas Cluster Tiers", "domain": "Capacity Planning",
        "prerequisites": "Atlas Project Owner API Keys",
        "steps": {"step1": "curl -X PATCH https://x/groups/$ATLAS_PROJECT_ID/clusters/$CLUSTER",
                  "step2": "curl https://x/groups/$ATLAS_PROJECT_ID/clusters/$CLUSTER",
                  "verify": "mongosh $MONGODB_URI --eval 'db.hostInfo()'"},
        "troubleshooting": {"error": "CANNOT_DOWNGRADE_BELOW_STORAGE", "solution": "Pick a tier that fits."},
        "raw_markdown": "scaling cluster tiers storage",
    }
    base.update(kw)
    return base


class TestConfidence:
    def test_title_words_count_more(self, articles):
        kb16 = next(a for a in articles if a["doc_id"] == "KB-0016")
        assert match_confidence("private endpoint connection timeouts", kb16) == 1.0
        assert match_confidence("bake a chocolate cake", kb16) == 0.0

    def test_empty(self):
        assert match_confidence("", article()) == 0.0
        assert match_confidence("x", {}) == 0.0

    def test_body_match_counts_less(self):
        assert match_confidence("storages", article()) == 0.6


class TestChecklist:
    def test_structure_and_actors(self):
        steps = build_checklist(article(), related=[{"doc_id": "KB-0038", "title": "Storage"}])
        ids = [s["id"] for s in steps]
        assert ids == ["agent-review", "agent-memory", "pre-1", "pre-2", "pre-3", "step-1", "step-2", "verify"]
        assert all(s["actor"] == "human" for s in steps if s["command"])
        assert steps[0]["status"] == "done" and "KB-0038" in steps[0]["output"]

    def test_uses_prerequisite_items_when_parsed(self, articles):
        steps = build_checklist(articles[0], memory_on=False)
        assert [s["id"] for s in steps][:2] == ["agent-review", "pre-1"]
        assert "Terraform CLI" in steps[1]["title"]

    def test_no_related(self):
        assert "No related" in build_checklist(article())[0]["output"]

    def test_explanations_override(self):
        steps = build_checklist(article(), explanations={"step-1": "custom"})
        assert next(s for s in steps if s["id"] == "step-1")["explain"] == "custom"

    def test_skips_missing_commands(self):
        steps = build_checklist(article(steps={"step1": "az login", "step2": "", "verify": ""}))
        assert [s["id"] for s in steps if s["kind"] in ("step", "verify")] == ["step-1"]

    def test_memory_counts(self):
        hits = [hit(), hit(type="procedural", label="KB-0020:step-1", content="note",
                           source={"doc_id": "KB-0020", "step_id": "step-1"}), hit(type="episodic", label="r")]
        out = build_checklist(article(), hits=hits)[1]["output"]
        assert out == "1 note on this procedure, 1 fact, 1 past run."


class TestHints:
    def test_fact_fills_matching_variable(self):
        hints = memory_hints("step-1", "curl $CLUSTER", "KB-0020", [hit()])
        assert hints == ["Known value for $CLUSTER from memory: kbase-prod"]

    def test_suffix_match(self):
        hints = memory_hints("step-1", "curl $ATLAS_PROJECT_ID", "KB-0020",
                             [hit(label="project id", content="project id = 6a66")])
        assert hints == ["Known value for $ATLAS_PROJECT_ID from memory: 6a66"]

    def test_secret_variables_never_filled(self):
        hints = memory_hints("verify", "mongosh $MONGODB_URI", "KB-0020",
                             [hit(label="mongodb uri", content="mongodb uri = x")])
        assert len(hints) == 1 and "never fills" in hints[0]

    def test_procedural_note_for_same_step(self):
        note = hit(type="procedural", label="KB-0020:step-2", content="needed a bigger disk",
                   source={"doc_id": "KB-0020", "step_id": "step-2"})
        assert memory_hints("step-2", "", "KB-0020", [note]) == ["From a past run: needed a bigger disk"]
        assert memory_hints("step-1", "", "KB-0020", [note]) == []

    def test_no_match(self):
        assert memory_hints("step-1", "curl $REGION", "KB-0020", [hit(type="episodic", label=None)]) == []


class TestGuidance:
    def test_combines_sources(self):
        note = hit(type="procedural", label="KB-0020:verify", content="check disk", source={"doc_id": "KB-0020"})
        out = failure_guidance(article(), {}, related=[{"doc_id": "KB-0038", "title": "Storage"}], hits=[note])
        assert out[0].startswith("Known error") and out[1] == "From a past run: check disk"
        assert out[2] == "Related article: KB-0038 Storage"

    def test_fallback_message(self):
        out = failure_guidance(article(troubleshooting={}), {}, related=[], hits=[])
        assert "escalate" in out[0]
