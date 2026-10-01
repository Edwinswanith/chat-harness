import asyncio
from app.schemas.contracts import SubAgentResult


class SubAgentManager:
    def __init__(self, registry, repo, model, publisher=None):
        self.registry, self.repo, self.model = registry, repo, model
        self.publisher = publisher

    async def run_agent(self, name, scope, run, feedback) -> SubAgentResult:
        record = await self.repo.create("subagent_run", scope, run["thread_id"], run_id=run["id"],
                                        name=name, status="running")
        if self.publisher:
            await self.publisher.emit(run_id=run['id'], event_type='agent.started', component='subagent', component_name=name, status='started', summary=name + ' started', details={'agent_id':record['id'], 'agent_name':name})
        try:
            result = await self.registry.get(name).run(self.model, run, feedback)
            await self.repo.patch("subagent_run", record["id"], scope, status=result.status,
                                  feedback=result.feedback)
            if self.publisher:
                await self.publisher.emit(run_id=run['id'], event_type='agent.completed', component='subagent', component_name=name, status='failed' if result.status == 'error' else 'success', summary=name + ' finished', details={'agent_id':record['id'], 'agent_name':name})
            return result
        except asyncio.CancelledError:
            await self.repo.patch('subagent_run', record['id'], scope, status='cancelled')
            if self.publisher:
                await self.publisher.emit(run_id=run['id'], event_type='agent.cancelled', component='subagent', component_name=name, status='cancelled', summary=name + ' cancelled', details={'agent_id':record['id'], 'agent_name':name})
            raise
        except Exception as exc:
            result = SubAgentResult(status="error", feedback=str(exc)[:500])
            await self.repo.patch("subagent_run", record["id"], scope, status="error",
                                  feedback=result.feedback)
            if self.publisher:
                await self.publisher.emit(run_id=run['id'], event_type='agent.failed', component='subagent', component_name=name, status='failed', summary=name + ' failed', details={'agent_id':record['id'], 'agent_name':name})
            return result
