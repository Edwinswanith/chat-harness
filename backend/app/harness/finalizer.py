class Finalizer:
    def __init__(self, runs, repo):
        self.runs, self.repo = runs, repo

    async def complete(self, run, scope, text, artifact_ids, sources):
        current = await self.repo.get("run", run["id"], scope)
        if current.get("task_classification", {}).get("requires_full_project") and not current.get("website_validation", {}).get("passed"):
            raise ValueError("Website completion contract must pass before finalization")
        blocks = []
        for artifact_id in dict.fromkeys(artifact_ids):
            artifact = await self.repo.get("artifact", artifact_id, scope)
            blocks.append({"type": "artifact", "id": artifact_id, "name": artifact["name"],
                           "media_type": artifact.get("media_type", "text/plain")})
        for source in sources:
            blocks.append({"type": "source", "id": source["source_id"], "name": source["name"]})
        return await self.runs.finish(run["id"], scope, text, blocks)
