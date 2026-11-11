"""
AgentAuth Policy Template Registry.

Pre-built, production-ready natural language policy rule sets based on
African regulatory frameworks — starting with the National Bank of Ethiopia (NBE).

Templates give developers a compliant starting point in one line:

    from agentauth.templates import PolicyTemplate, registry

    template = registry.get(PolicyTemplate.NBE_PAYMENT_AGENT)
    rules = template.rules  # full NBE-compliant rule set

Templates can be customised with overrides — additional rules that are
appended to the base template, or replacements using the override mechanism:

    rules = registry.build_rules(
        PolicyTemplate.NBE_PAYMENT_AGENT,
        overrides=["Agent may process payments up to ETB 500,000 per transaction"]
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PolicyTemplate(str, Enum):
    """
    Available policy templates.

    Naming convention: <REGULATOR>_<USE_CASE>
    """
    # ── National Bank of Ethiopia (NBE) ───────────────────────────────────────
    NBE_PAYMENT_AGENT      = "nbe_payment_agent"
    NBE_FOREX_AGENT        = "nbe_forex_agent"
    NBE_LENDING_AGENT      = "nbe_lending_agent"
    NBE_KYC_AGENT          = "nbe_kyc_agent"
    NBE_AUDIT_AGENT        = "nbe_audit_agent"
    NBE_MOBILE_BANKING     = "nbe_mobile_banking"
    NBE_INSURANCE_AGENT    = "nbe_insurance_agent"


@dataclass
class TemplateDefinition:
    """
    A single policy template definition.

    Attributes:
        name:        The PolicyTemplate enum value (also the lookup key).
        display_name: Human-readable name shown in the API.
        description: Short description of what this template governs.
        regulator:   The regulatory body this template is based on.
        jurisdiction: Country / region.
        version:     Template version (bump when rules change).
        rules:       The base set of natural language policy rules.
        tags:        Searchable topic tags.
        references:  Official directive or document references.
    """
    name: PolicyTemplate
    display_name: str
    description: str
    regulator: str
    jurisdiction: str
    version: str
    rules: list[str]
    tags: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict for the API response."""
        return {
            "name": self.name.value,
            "display_name": self.display_name,
            "description": self.description,
            "regulator": self.regulator,
            "jurisdiction": self.jurisdiction,
            "version": self.version,
            "rules": self.rules,
            "tags": self.tags,
            "references": self.references,
            "rule_count": len(self.rules),
        }


class TemplateRegistry:
    """
    Central registry for all policy templates.

    Templates are registered at import time by provider modules (e.g. nbe.py).
    The registry is a singleton accessed via the module-level ``registry`` object.

    Usage:
        from agentauth.templates import PolicyTemplate, registry

        # List all available templates
        all_templates = registry.list_all()

        # Fetch a specific template
        template = registry.get(PolicyTemplate.NBE_PAYMENT_AGENT)

        # Build a final rule list (base + optional overrides appended)
        rules = registry.build_rules(
            PolicyTemplate.NBE_PAYMENT_AGENT,
            overrides=["Agent may process payments up to ETB 500,000"]
        )

        # Look up by string name (useful in API handlers)
        template = registry.get_by_name("nbe_payment_agent")
    """

    def __init__(self) -> None:
        self._templates: dict[PolicyTemplate, TemplateDefinition] = {}

    def register(self, template: TemplateDefinition) -> None:
        """Register a template. Called by provider modules at import time."""
        self._templates[template.name] = template

    def get(self, name: PolicyTemplate) -> TemplateDefinition:
        """
        Return a template by its enum value.
        Raises KeyError if not found.
        """
        if name not in self._templates:
            raise KeyError(f"Template '{name.value}' is not registered.")
        return self._templates[name]

    def get_by_name(self, name: str) -> TemplateDefinition | None:
        """
        Return a template by its string name, or None if not found.
        Case-insensitive.
        """
        normalised = name.lower().strip()
        for key, template in self._templates.items():
            if key.value == normalised:
                return template
        return None

    def list_all(self) -> list[TemplateDefinition]:
        """Return all registered templates sorted by name."""
        return sorted(self._templates.values(), key=lambda t: t.name.value)

    def list_by_regulator(self, regulator: str) -> list[TemplateDefinition]:
        """Return all templates for a given regulator (case-insensitive)."""
        normalised = regulator.lower().strip()
        return [
            t for t in self._templates.values()
            if t.regulator.lower() == normalised
        ]

    def list_by_tag(self, tag: str) -> list[TemplateDefinition]:
        """Return all templates that include a given tag."""
        normalised = tag.lower().strip()
        return [
            t for t in self._templates.values()
            if normalised in [tg.lower() for tg in t.tags]
        ]

    def build_rules(
        self,
        name: PolicyTemplate,
        overrides: list[str] | None = None,
    ) -> list[str]:
        """
        Return the final rule list for a template, with optional overrides appended.

        Overrides are additional rules added after the base template rules.
        They do not replace base rules — use them to tighten constraints
        specific to your deployment (e.g. lower transaction limits).

        Args:
            name:      The template to use as the base.
            overrides: Additional rules to append. Optional.

        Returns:
            Combined list of rules (base + overrides).
        """
        template = self.get(name)
        rules = list(template.rules)
        if overrides:
            rules.extend(overrides)
        return rules

    @property
    def count(self) -> int:
        return len(self._templates)


# ── Module-level singleton ─────────────────────────────────────────────────────
registry = TemplateRegistry()

# Import provider modules to trigger registration
# (must come after registry is defined)
from agentauth.templates import nbe  # noqa: E402, F401
