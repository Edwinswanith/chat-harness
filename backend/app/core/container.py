import os
from pathlib import Path

from app.core.config import Settings
from app.core.security import TokenAuthenticator
from app.harness.context_builder import ContextBuilder
from app.harness.finalizer import Finalizer
from app.harness.orchestrator import RunOrchestrator
from app.harness.planner import Planner
from app.memory.memory_service import MemoryService
from app.model_clients.gemini_client import GeminiModelClient
from app.model_clients.gemini_document_extractor import GeminiDocumentExtractor
from app.model_clients.gemini_image_client import GeminiImageClient
from app.queue.job_queue import JobQueue
from app.rag.embeddings import GeminiEmbeddings
from app.rag.ingestion_service import IngestionService
from app.rag.rag_service import RagService
from app.rag.vector_store import SqliteVectorStore
from app.rag.mongo_vector_store import MongoVectorStore
from app.repositories.database import Database
from app.repositories.entity_repository import EntityRepository
from app.repositories.mongo_repository import MongoEntityRepository, ensure_indexes
from app.repositories.mongo_run_repository import MongoRunRepository
from app.repositories.run_repository import RunRepository
from app.services.artifact_service import ArtifactService
from app.services.chat_service import ChatService
from app.services.file_service import FileService
from app.services.job_service import JobService
from app.services.run_service import RunService
from app.services.sandbox_client import HttpSandboxClient
from app.storage.local_storage import LocalStorage
from app.storage.r2_storage import R2Storage
from app.subagents.base import ReviewerAgent
from app.subagents.manager import SubAgentManager
from app.subagents.registry import SubAgentRegistry
from app.tools.calculator import Calculator
from app.tools.create_artifact import CreateArtifact
from app.tools.generate_image import GenerateImage
from app.tools.tool_orchestrator import ToolOrchestrator
from app.tools.tool_registry import ToolRegistry
from app.tools.workspace_tools import ListDirectory, ReadFile, SearchText, WriteFile, CreateFile, CreateDirectory, RenamePath, DeletePath, PatchFile, RunBuild, RunTests, RunLint, RunCommand
from app.validation.validation_service import ValidationService
from app.workers.job_worker import JobWorker
from app.workspaces.provider import LocalWorkspaceProvider
from app.workspaces.service import WorkspaceService
from app.workspaces.website_workflow import WebsiteWorkflow


class AppContainer:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        host_data_dir = Path(os.getenv("DATA_DIR", "/tmp/ai-harness"))
        use_remote = self.settings.persistence_mode == "mongo" or (
            self.settings.persistence_mode == "auto" and self.settings.data_dir == host_data_dir)
        if use_remote and self.settings.mongodb_uri:
            from pymongo import MongoClient
            client = MongoClient(self.settings.mongodb_uri, serverSelectionTimeoutMS=5000)
            database = client[self.settings.mongodb_database]
            ensure_indexes(database)
            self.repo = MongoEntityRepository(database)
            runs = MongoRunRepository(database, self.repo)
            vectors = MongoVectorStore(database)
            self.mongo_client = client
        else:
            database = Database(self.settings.data_dir / "harness.db")
            self.repo = EntityRepository(database)
            runs = RunRepository(database, self.repo)
            vectors = SqliteVectorStore(database)
            self.mongo_client = None
        self.run_service = RunService(runs, self.repo)
        self.authenticator = TokenAuthenticator(self.settings.tokens)
        self.queue = JobQueue()
        if use_remote and self.settings.r2_bucket and self.settings.r2_endpoint_url and self.settings.r2_access_key_id and self.settings.r2_secret_access_key:
            storage = R2Storage(self.settings.r2_bucket, self.settings.r2_endpoint_url,
                                self.settings.r2_access_key_id, self.settings.r2_secret_access_key)
        else:
            storage = LocalStorage(self.settings.data_dir / "storage")
        self.jobs = JobService(self.repo, self.queue)
        self.workspaces = WorkspaceService(self.repo, LocalWorkspaceProvider())
        self.website_workflow = WebsiteWorkflow(self.workspaces, self.repo, self.run_service.publisher)
        self.files = FileService(self.repo, storage, self.jobs, self.settings.max_upload_bytes)
        self.artifacts = ArtifactService(self.repo, storage)
        embeddings = GeminiEmbeddings(self.settings.gemini_api_key, self.settings.embedding_model)
        extractor = GeminiDocumentExtractor(self.settings.gemini_api_key, self.settings.gemini_model)
        ingestion = IngestionService(self.repo, storage, vectors, embeddings, extractor)
        self.rag = RagService(vectors, embeddings, self.files)
        sandbox = HttpSandboxClient(self.settings.sandbox_url, self.settings.sandbox_token)
        self.worker = JobWorker(self.queue, self.repo, sandbox, self.artifacts, ingestion, self.run_service.publisher)
        model = GeminiModelClient(self.settings.gemini_api_key, self.settings.gemini_model)
        self.website_workflow.model = model
        self.website_workflow.image_generation_available = bool(self.settings.gemini_api_key)
        images = GeminiImageClient(self.settings.gemini_api_key, self.settings.image_model)
        registry = ToolRegistry([Calculator(), CreateArtifact(self.jobs, self.files), GenerateImage(images, self.artifacts, self.workspaces),
            ListDirectory(self.workspaces), ReadFile(self.workspaces), SearchText(self.workspaces), WriteFile(self.workspaces),
            CreateFile(self.workspaces), CreateDirectory(self.workspaces), RenamePath(self.workspaces), DeletePath(self.workspaces), PatchFile(self.workspaces), RunBuild(self.workspaces), RunTests(self.workspaces), RunLint(self.workspaces), RunCommand(self.workspaces)])
        tools = ToolOrchestrator(registry, self.repo, self.run_service, self.settings.max_steps,
                                 self.settings.workspace_max_steps * 2)
        subagents = SubAgentManager(SubAgentRegistry([ReviewerAgent()]), self.repo, model, self.run_service.publisher)
        self.chat = ChatService(self.repo, runs, self.files)
        self.chat.orchestrator = RunOrchestrator(
            Planner(), ContextBuilder(), MemoryService(self.repo), self.rag, model, tools, subagents,
            ValidationService(), Finalizer(runs, self.repo), self.run_service, self.settings, self.website_workflow)

    async def start(self):
        await self.run_service.repository.recover()
        self.worker.start()

    async def close(self):
        await self.chat.close()
        await self.worker.close()
        if self.mongo_client:
            self.mongo_client.close()
