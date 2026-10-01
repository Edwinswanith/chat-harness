class ToolRegistry:
    def __init__(self, tools):
        self.tools = {tool.name: tool for tool in tools}

    def get(self, name, mode=None):
        if name not in self.tools:
            raise ValueError("Unknown tool: " + name)
        tool = self.tools[name]
        if mode and mode not in getattr(tool, "modes", {"chatbot", "workspace"}):
            raise ValueError("Tool is not available in this mode")
        return tool

    def describe(self, mode=None):
        return [{"name": t.name, "description": t.description, "parameters": t.schema.model_json_schema()}
                for t in self.tools.values() if not mode or mode in getattr(t, "modes", {"chatbot", "workspace"})]
