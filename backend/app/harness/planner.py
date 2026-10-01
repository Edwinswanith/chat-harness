class Planner:
    async def create_plan(self, request):
        from app.workspaces.website_workflow import WebsiteWorkflow
        from app.workspaces.completion_contract import STEPS
        import json
        if WebsiteWorkflow.classify(request.get("text", ""))["requires_full_project"]:
            return json.dumps({"task_type": "website_generation", "steps": STEPS,
                               "success": "All planned outputs, build, preview and desktop/mobile visual QA pass"})
        if request.get("file_ids"):
            return "Retrieve approved sources, create report, validate, finalize."
        return "Build context, choose direct answer or tool, validate, finalize."
