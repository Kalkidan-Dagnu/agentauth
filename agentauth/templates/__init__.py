"""
AgentAuth Policy Templates.

Pre-built natural language policy rule sets based on African regulatory
frameworks. Includes NBE Ethiopia (7 templates) and CBN Nigeria (5 templates).

Quick start:

    from agentauth.templates import PolicyTemplate, registry

    # List all available templates
    for t in registry.list_all():
        print(t.name.value, "-", t.display_name)

    # Get rules for a specific template
    template = registry.get(PolicyTemplate.NBE_PAYMENT_AGENT)
    print(template.rules)

    # Build rules with custom overrides
    rules = registry.build_rules(
        PolicyTemplate.NBE_MOBILE_BANKING,
        overrides=["Agent may not process transactions above ETB 10,000 without OTP"]
    )
"""

from agentauth.templates.registry import (
    PolicyTemplate,
    TemplateDefinition,
    TemplateRegistry,
    registry,
)

__all__ = [
    "PolicyTemplate",
    "TemplateDefinition",
    "TemplateRegistry",
    "registry",
]
