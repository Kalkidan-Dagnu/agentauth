"""
AgentAuth — Open-source identity and authentication layer for AI agents.
Powered by Google Gemini. Built by Kibrnet PLC, Addis Ababa, Ethiopia.
"""

from agentauth.core.engine import AgentAuthEngine
from agentauth.core.models import (
    Agent,
    AgentIdentity,
    Permission,
    PermissionDecision,
    Policy,
)
from agentauth.sdk.client import AgentAuthClient

__version__ = "0.1.0"
__author__ = "Kalkidan Dagnu <kalajanegassykoki@gmail.com>"
__license__ = "MIT"

__all__ = [
    "AgentAuthEngine",
    "AgentAuthClient",
    "Agent",
    "AgentIdentity",
    "Permission",
    "PermissionDecision",
    "Policy",
]
