"""SC-003: for tasks written in different words from the article titles, the agent picks the
intended procedure first at least 8 times out of 10 (offline mode, no LLM)."""
from kbase.agent.engine import AgentEngine
from kbase.agent.runs import InMemoryRunStore
from kbase.agent.sop_agent import SOPAgent

TASKS = [
    ("spin up a new Atlas cluster using infrastructure as code", "KB-0001"),
    ("connect Atlas to our Azure VNet over a private link", "KB-0002"),
    ("turn on automatic voyage embeddings for vector search", "KB-0003"),
    ("make sure every resource carries the right cost center tag", "KB-0005"),
    ("trigger the KB ingest pipeline from a GitHub webhook", "KB-0006"),
    ("stream changes from Postgres into Mongo with Kafka", "KB-0007"),
    ("enforce TLS 1.3 on the replica set", "KB-0013"),
    ("logs older than 30 days should expire automatically", "KB-0019"),
    ("move the cluster to a bigger tier through the API", "KB-0020"),
    ("rotate the service account keys automatically", "KB-0035"),
]


def test_agent_picks_intended_procedure(offline_kb):
    agent = SOPAgent(lambda name: AgentEngine(offline_kb), InMemoryRunStore())
    picked = [(agent.start(task, "eval").get("procedure") or {}).get("doc_id") for task, _ in TASKS]
    correct = sum(got == want for got, (_, want) in zip(picked, TASKS))
    assert correct >= 8, list(zip(picked, TASKS))
