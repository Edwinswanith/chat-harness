import asyncio
import base64
import json
import re

import pytest

from app.core.config import Settings
from app.harness.context_builder import ContextBuilder
from app.harness.finalizer import Finalizer
from app.harness.orchestrator import RunOrchestrator
from app.harness.planner import Planner
from app.memory.memory_service import MemoryService
from app.queue.job_queue import JobQueue
from app.rag.embeddings import GeminiEmbeddings
from app.rag.ingestion_service import IngestionService
from app.rag.rag_service import RagService
from app.rag.vector_store import SqliteVectorStore
from app.repositories.database import Database
from app.repositories.entity_repository import EntityRepository
from app.repositories.run_repository import RunRepository
from app.schemas.contracts import Decision, MessageRequest, Scope
from app.services.artifact_service import ArtifactService
from app.services.chat_service import ChatService
from app.services.file_service import FileService
from app.services.job_service import JobService
from app.services.run_service import RunService
from app.storage.local_storage import LocalStorage
from app.subagents.base import ReviewerAgent
from app.subagents.manager import SubAgentManager
from app.subagents.registry import SubAgentRegistry
from app.tools.calculator import Calculator
from app.tools.create_artifact import CreateArtifact
from app.tools.tool_orchestrator import ToolOrchestrator
from app.tools.tool_registry import ToolRegistry
from app.validation.validation_service import ValidationService
from app.workers.job_worker import JobWorker


class FakeEmbeddings:
    async def embed_documents(self, texts):
        return [self.vector(text) for text in texts]

    async def embed_query(self, text):
        return self.vector(text)

    @staticmethod
    def vector(text):
        words = set(text.lower().split())
        return [1.0 if "orbital" in words else 0.0, 1.0 if "garden" in words else 0.0, 1.0]


class FakeSandbox:
    async def execute(self, code, inputs):
        match = re.search(r"Path\('/output/([^']+)'\)\.write_text\((.*), encoding", code)
        name, content = match.group(1), json.loads(match.group(2))
        return {"exit_code": 0, "stderr": "", "outputs": [
            {"name": name, "content_base64": base64.b64encode(content.encode()).decode()}]}


class ScriptedModel:
    def __init__(self):
        self.contexts = []

    async def call(self, context):
        self.contexts.append(context)
        text = context.request["text"].lower()
        if "website" in text and not context.results:
            return Decision(kind="tool", name="create_artifact", arguments={
                "name": "website.md", "content": "# Product website\n\nLanding page copy", "source_ids": []})
        if "website" in text:
            return Decision(kind="final", text="Website specification is ready.")
        if "review" in text and not context.feedback:
            return Decision(kind="subagent", name="reviewer", text="Check the request")
        if "review" in text:
            return Decision(kind="final", text="Review completed after specialist feedback.")
        if "research" in text:
            return Decision(kind="final", text="Research result based on the attached source.")
        return Decision(kind="final", text="Memory-aware response.")

    async def review(self, prompt):
        return "Use a concise, validated response."


async def wait_for_status(runs, run_id, scope):
    for _ in range(100):
        run = await runs.get(run_id, scope)
        if run["status"] in {"completed", "failed", "cancelled"}:
            return run
        await asyncio.sleep(0.02)
    raise AssertionError("run did not finish")


async def wait_for_file(files, file_id, scope, thread_id):
    for _ in range(100):
        source = await files.get_source(file_id, scope, thread_id)
        if source["status"] in {"indexed", "failed"}:
            return source
        await asyncio.sleep(0.02)
    raise AssertionError("source did not finish indexing")


async def build_harness(tmp_path):
    database = Database(tmp_path / "harness.db")
    repo, runs = EntityRepository(database), RunRepository(database, None)
    run_service = RunService(runs, repo)
    queue, storage = JobQueue(), LocalStorage(tmp_path / "storage")
    jobs = JobService(repo, queue)
    files = FileService(repo, storage, jobs, 500_000)
    artifacts = ArtifactService(repo, storage)
    vectors, embeddings = SqliteVectorStore(database), FakeEmbeddings()
    ingestion = IngestionService(repo, storage, vectors, embeddings)
    worker = JobWorker(queue, repo, FakeSandbox(), artifacts, ingestion)
    model = ScriptedModel()
    rag = RagService(vectors, embeddings, files)
    tools = ToolOrchestrator(ToolRegistry([Calculator(), CreateArtifact(jobs, files)]), repo, run_service)
    subagents = SubAgentManager(SubAgentRegistry([ReviewerAgent()]), repo, model)
    orchestrator = RunOrchestrator(Planner(), ContextBuilder(), MemoryService(repo), rag, model, tools,
        subagents, ValidationService(), Finalizer(runs, repo), run_service, Settings(data_dir=tmp_path))
    chat = ChatService(repo, runs, files)
    chat.orchestrator = orchestrator
    worker.start()
    return repo, run_service, chat, files, artifacts, worker, model


def test_website_artifact_run_end_to_end(tmp_path):
    asyncio.run(website_scenario(tmp_path))


async def website_scenario(tmp_path):
    repo, runs, chat, _, artifacts, worker, _ = await build_harness(tmp_path)
    scope = Scope(user_id="alice", workspace_id="site")
    thread = await chat.create_thread(scope)
    run = await chat.submit(scope, MessageRequest(thread_id=thread["id"], text="Build a website brief",
                                                   idempotency_key="website"))
    assert (await wait_for_status(runs, run["id"], scope))["status"] == "completed"
    message = (await chat.messages(scope, thread["id"]))[-1]
    artifact_id = next(block["id"] for block in message["blocks"] if block["type"] == "artifact")
    _, data = await artifacts.download(artifact_id, scope)
    assert b"Product website" in data
    await worker.close(); await chat.close()


def test_research_rag_scope_and_source_cards(tmp_path):
    asyncio.run(research_scenario(tmp_path))


async def research_scenario(tmp_path):
    repo, runs, chat, files, _, worker, _ = await build_harness(tmp_path)
    alice = Scope(user_id="alice", workspace_id="research")
    thread = await chat.create_thread(alice)
    source = await files.upload(alice, thread["id"], "orbit.md", b"orbital mission research evidence")
    assert (await wait_for_file(files, source["id"], alice, thread["id"]))["status"] == "indexed"
    run = await chat.submit(alice, MessageRequest(thread_id=thread["id"], text="Research orbital mission",
                                                   idempotency_key="research", file_ids=[source["id"]]))
    assert (await wait_for_status(runs, run["id"], alice))["status"] == "completed"
    user_message = (await chat.messages(alice, thread["id"]))[-2]
    assert user_message["blocks"] == [{"type": "source", "id": source["id"], "name": "orbit.md", "status": "indexed"}]
    message = (await chat.messages(alice, thread["id"]))[-1]
    assert any(block["type"] == "source" and block["name"] == "orbit.md" for block in message["blocks"])
    with pytest.raises(KeyError):
        await files.get_source(source["id"], Scope(user_id="bob", workspace_id="research"), thread["id"])
    await worker.close(); await chat.close()


def test_memory_and_reviewer_subagent_are_used_when_requested(tmp_path):
    asyncio.run(memory_and_review_scenario(tmp_path))


async def memory_and_review_scenario(tmp_path):
    repo, runs, chat, _, _, worker, model = await build_harness(tmp_path)
    scope = Scope(user_id="alice", workspace_id="memory")
    thread = await chat.create_thread(scope)
    first = await chat.submit(scope, MessageRequest(thread_id=thread["id"], text="Remember my green garden",
                                                     idempotency_key="memory-1"))
    assert (await wait_for_status(runs, first["id"], scope))["status"] == "completed"
    review = await chat.submit(scope, MessageRequest(thread_id=thread["id"], text="Review this plan",
                                                      idempotency_key="review-1"))
    assert (await wait_for_status(runs, review["id"], scope))["status"] == "completed"
    assert any(item["text"] == "Remember my green garden" for context in model.contexts for item in context.memory.recent)
    agent_runs = await repo.list("subagent_run", scope, thread["id"])
    assert len(agent_runs) == 1 and agent_runs[0]["name"] == "reviewer"
    await worker.close(); await chat.close()
