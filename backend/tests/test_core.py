import asyncio
from types import SimpleNamespace
import pytest
from app.core.config import Settings
from app.repositories.database import Database
from app.repositories.entity_repository import EntityRepository
from app.repositories.run_repository import RunRepository
from app.schemas.contracts import Scope, MessageRequest, RagContext
from app.harness.orchestrator import RunOrchestrator
from app.harness.context_builder import ContextBuilder
from app.harness.planner import Planner
from app.harness.finalizer import Finalizer
from app.memory.memory_service import MemoryService
from app.model_clients.mock_client import MockModelClient
from app.services.run_service import RunService
from app.validation.validation_service import ValidationService


def test_core_chat_and_atomic_duplicate(tmp_path):
    asyncio.run(core_scenario(tmp_path))


async def core_scenario(tmp_path):
    db = Database(tmp_path / 'test.db')
    repo = EntityRepository(db)
    runs = RunRepository(db, repo)
    scope = Scope(user_id='alice', workspace_id='one')
    thread = await repo.create('thread', scope, '', title='test')
    request = MessageRequest(thread_id=thread['id'], text='Hello', idempotency_key='first')
    first, duplicate = await asyncio.gather(runs.submit(scope, request), runs.submit(scope, request))
    assert first['id'] == duplicate['id']
    pending = await repo.list('message', scope, thread['id'])
    assert len(pending) == 2 and pending[-1]['status'] == 'streaming'

    class Rag:
        async def retrieve(self, *args):
            return RagContext()

    orchestrator = RunOrchestrator(Planner(), ContextBuilder(), MemoryService(repo), Rag(),
        MockModelClient(), SimpleNamespace(describe=lambda: []), None, ValidationService(),
        Finalizer(runs, repo), RunService(runs, repo), Settings(data_dir=tmp_path))
    await asyncio.gather(orchestrator.run(first['id'], scope), orchestrator.run(first['id'], scope))
    assert (await repo.get('run', first['id'], scope))['status'] == 'completed'
    completed = await repo.list('message', scope, thread['id'])
    assert len(completed) == 2 and completed[-1]['status'] == 'completed'
    with pytest.raises(KeyError):
        await repo.get('run', first['id'], Scope(user_id='bob', workspace_id='one'))
    assert any(e['event'] == 'delta' for e in await runs.events(first['id']))
