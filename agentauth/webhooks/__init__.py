"""
AgentAuth webhooks package.

Handles delivery of PermissionDecision payloads to registered webhook URLs.
"""

from agentauth.webhooks.dispatcher import dispatch_webhooks

__all__ = ["dispatch_webhooks"]
