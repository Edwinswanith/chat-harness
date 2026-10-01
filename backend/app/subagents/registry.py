class SubAgentRegistry:
    def __init__(self, agents):
        self.agents = {agent.name: agent for agent in agents}

    def get(self, name):
        if name not in self.agents:
            raise ValueError("Unknown sub-agent: " + name)
        return self.agents[name]
