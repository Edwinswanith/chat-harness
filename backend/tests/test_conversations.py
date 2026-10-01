import asyncio

from app.core.config import Settings
from app.repositories.database import Database
from app.repositories.entity_repository import EntityRepository
from app.repositories.run_repository import RunRepository
from app.schemas.contracts import MessageRequest, Scope
from app.services.chat_service import ChatService


def test_conversations_are_scoped_and_durable(tmp_path):
    asyncio.run(scenario(tmp_path))


async def scenario(tmp_path):
    repo = EntityRepository(Database(tmp_path / "conversations.db"))
    chat = ChatService(repo, RunRepository(repo.db, repo), None)
    alice, bob = Scope(user_id="alice", workspace_id="one"), Scope(user_id="bob", workspace_id="one")
    first, second = await chat.create_thread(alice), await chat.create_thread(alice)
    assert first["conversation_id"] == first["id"]
    await chat.runs.submit(alice, MessageRequest(thread_id=first["id"], text="First conversation", idempotency_key="one"))
    await chat.runs.submit(alice, MessageRequest(thread_id=second["id"], text="Second conversation", idempotency_key="two"))
    assert [item["id"] for item in await chat.conversations(alice)] == [second["id"], first["id"]]
    assert len((await chat.paged_messages(alice, first["id"]))["items"]) == 2
    try:
        await chat.conversation(bob, first["id"])
    except KeyError:
        pass
    else:
        raise AssertionError("cross-user conversation access was allowed")
    await chat.update_conversation(alice, second["id"], status="archived")
    assert [item["id"] for item in await chat.conversations(alice)] == [first["id"]]
