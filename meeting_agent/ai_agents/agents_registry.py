from typing import Dict, Type
from project_manager_agent.ai_agents.base_agent import BaseAgent


class ExecAgentRegistry:
    _agents: Dict[str, Type[BaseAgent]] = {}

    @classmethod
    def register(cls, agent_name: str, agent_class: Type[BaseAgent]):
        cls._agents[agent_name] = agent_class

    @classmethod
    def get_agent(cls, agent_name: str) -> BaseAgent:
        if agent_name not in cls._agents:
            raise KeyError(f"Exec agent '{agent_name}' is not registered")
        return cls._agents[agent_name]()

    @classmethod
    def list_agents(cls) -> list:
        return list(cls._agents.keys())

    @classmethod
    def is_registered(cls, agent_name: str) -> bool:
        return agent_name in cls._agents
