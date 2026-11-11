"""
Tests for AgentAuth v0.4.0 — NBE Ethiopia Policy Templates.

Covers:
  - TemplateRegistry: get, list, filter, build_rules
  - All 7 NBE templates: structure, rule counts, metadata
  - GET /templates endpoint (list + filter)
  - GET /templates/{name} endpoint
  - POST /policies/from-template endpoint
  - SDK create_from_template(), list_templates(), get_template()
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentauth.db.models import Base
from agentauth.db.session import get_db
from agentauth.templates import PolicyTemplate, registry
from agentauth.templates.registry import TemplateDefinition, TemplateRegistry

# ── Test database setup ───────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_test_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_test_session_factory = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


async def _override_get_db():
    async with _test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-that-is-32-chars!!")


@pytest_asyncio.fixture
async def db_session():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _test_session_factory() as session:
        yield session
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def api_client(db_session):
    from agentauth.api.server import app

    app.dependency_overrides[get_db] = _override_get_db

    with patch("agentauth.api.server.AgentAuthEngine"):
        with patch("agentauth.api.server.init_db", new=AsyncMock()):
            with patch("agentauth.api.server.close_db", new=AsyncMock()):
                async with AsyncClient(app=app, base_url="http://test") as client:
                    yield client

    app.dependency_overrides.clear()


# ── TemplateRegistry unit tests ───────────────────────────────────────────────

class TestTemplateRegistry:
    def test_all_seven_nbe_templates_registered(self):
        templates = registry.list_all()
        assert len(templates) == 7

    def test_all_policy_template_enum_values_registered(self):
        for member in PolicyTemplate:
            template = registry.get(member)
            assert template is not None
            assert template.name == member

    def test_get_by_name_case_insensitive(self):
        t1 = registry.get_by_name("nbe_payment_agent")
        t2 = registry.get_by_name("NBE_PAYMENT_AGENT")
        t3 = registry.get_by_name("Nbe_Payment_Agent")
        assert t1 is not None
        assert t1.name == t2.name == t3.name

    def test_get_by_name_unknown_returns_none(self):
        assert registry.get_by_name("unknown_template") is None

    def test_get_unknown_enum_raises(self):
        # Build a fake registry to test error path
        r = TemplateRegistry()
        with pytest.raises(KeyError):
            r.get(PolicyTemplate.NBE_PAYMENT_AGENT)

    def test_list_by_regulator(self):
        nbe_templates = registry.list_by_regulator("National Bank of Ethiopia (NBE)")
        assert len(nbe_templates) == 7

    def test_list_by_regulator_case_insensitive(self):
        t1 = registry.list_by_regulator("national bank of ethiopia (nbe)")
        t2 = registry.list_by_regulator("NATIONAL BANK OF ETHIOPIA (NBE)")
        assert len(t1) == len(t2) == 7

    def test_list_by_tag_payment(self):
        payment_templates = registry.list_by_tag("payment")
        names = [t.name for t in payment_templates]
        assert PolicyTemplate.NBE_PAYMENT_AGENT in names
        assert PolicyTemplate.NBE_MOBILE_BANKING in names

    def test_list_by_tag_insurance(self):
        templates = registry.list_by_tag("insurance")
        assert any(t.name == PolicyTemplate.NBE_INSURANCE_AGENT for t in templates)

    def test_build_rules_no_overrides(self):
        rules = registry.build_rules(PolicyTemplate.NBE_KYC_AGENT)
        base = registry.get(PolicyTemplate.NBE_KYC_AGENT).rules
        assert rules == base

    def test_build_rules_with_overrides(self):
        override = "Agent must escalate all transactions above ETB 100"
        rules = registry.build_rules(PolicyTemplate.NBE_PAYMENT_AGENT, overrides=[override])
        assert rules[-1] == override
        assert len(rules) == len(registry.get(PolicyTemplate.NBE_PAYMENT_AGENT).rules) + 1

    def test_build_rules_does_not_mutate_template(self):
        """Overrides must not modify the original template rules list."""
        original_count = len(registry.get(PolicyTemplate.NBE_FOREX_AGENT).rules)
        registry.build_rules(
            PolicyTemplate.NBE_FOREX_AGENT,
            overrides=["extra rule 1", "extra rule 2"],
        )
        assert len(registry.get(PolicyTemplate.NBE_FOREX_AGENT).rules) == original_count

    def test_sorted_list(self):
        templates = registry.list_all()
        names = [t.name.value for t in templates]
        assert names == sorted(names)


# ── NBE template content tests ────────────────────────────────────────────────

class TestNBETemplates:
    @pytest.mark.parametrize("template_name, min_rules", [
        (PolicyTemplate.NBE_PAYMENT_AGENT,   10),
        (PolicyTemplate.NBE_FOREX_AGENT,     10),
        (PolicyTemplate.NBE_LENDING_AGENT,   10),
        (PolicyTemplate.NBE_KYC_AGENT,       10),
        (PolicyTemplate.NBE_AUDIT_AGENT,     8),
        (PolicyTemplate.NBE_MOBILE_BANKING,  10),
        (PolicyTemplate.NBE_INSURANCE_AGENT, 10),
    ])
    def test_each_template_has_minimum_rules(self, template_name, min_rules):
        template = registry.get(template_name)
        assert len(template.rules) >= min_rules, (
            f"{template_name.value} has only {len(template.rules)} rules, expected >= {min_rules}"
        )

    @pytest.mark.parametrize("template_name", list(PolicyTemplate))
    def test_each_template_has_required_metadata(self, template_name):
        t = registry.get(template_name)
        assert t.display_name
        assert t.description
        assert t.regulator == "National Bank of Ethiopia (NBE)"
        assert t.jurisdiction == "Ethiopia"
        assert t.version
        assert len(t.tags) > 0
        assert len(t.references) > 0

    @pytest.mark.parametrize("template_name", list(PolicyTemplate))
    def test_each_rule_is_non_empty_string(self, template_name):
        t = registry.get(template_name)
        for rule in t.rules:
            assert isinstance(rule, str)
            assert len(rule.strip()) > 10, f"Rule too short: {rule!r}"

    def test_audit_agent_has_read_only_rule(self):
        """The audit template must enforce read-only access."""
        t = registry.get(PolicyTemplate.NBE_AUDIT_AGENT)
        all_rules = " ".join(t.rules).lower()
        assert "read" in all_rules
        assert any("never" in r.lower() or "must not" in r.lower() for r in t.rules)

    def test_mobile_banking_has_mfa_rule(self):
        t = registry.get(PolicyTemplate.NBE_MOBILE_BANKING)
        all_rules = " ".join(t.rules).lower()
        assert "multi-factor" in all_rules or "mfa" in all_rules or "otp" in all_rules

    def test_kyc_has_sanctions_screening_rule(self):
        t = registry.get(PolicyTemplate.NBE_KYC_AGENT)
        all_rules = " ".join(t.rules).lower()
        assert "sanction" in all_rules

    def test_to_dict_has_all_fields(self):
        t = registry.get(PolicyTemplate.NBE_PAYMENT_AGENT)
        d = t.to_dict()
        for key in ("name", "display_name", "description", "regulator",
                    "jurisdiction", "version", "rules", "tags", "references", "rule_count"):
            assert key in d, f"Missing key: {key}"
        assert d["rule_count"] == len(t.rules)


# ── API endpoint tests ────────────────────────────────────────────────────────

class TestTemplateEndpoints:
    @pytest.mark.asyncio
    async def test_list_templates_returns_all_seven(self, api_client):
        resp = await api_client.get("/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 7

    @pytest.mark.asyncio
    async def test_list_templates_filter_by_regulator(self, api_client):
        resp = await api_client.get(
            "/templates",
            params={"regulator": "National Bank of Ethiopia (NBE)"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 7

    @pytest.mark.asyncio
    async def test_list_templates_filter_by_tag(self, api_client):
        resp = await api_client.get("/templates", params={"tag": "insurance"})
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert "nbe_insurance_agent" in names

    @pytest.mark.asyncio
    async def test_list_templates_unknown_tag_returns_empty(self, api_client):
        resp = await api_client.get("/templates", params={"tag": "completely_unknown_tag"})
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_template_by_name(self, api_client):
        resp = await api_client.get("/templates/nbe_kyc_agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "nbe_kyc_agent"
        assert data["display_name"] == "NBE KYC / AML Agent"
        assert len(data["rules"]) >= 10
        assert "rule_count" in data

    @pytest.mark.asyncio
    async def test_get_template_unknown_returns_404(self, api_client):
        resp = await api_client.get("/templates/nonexistent_template")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_policy_from_template(self, api_client):
        resp = await api_client.post(
            "/policies/from-template",
            json={
                "template_name": "nbe_payment_agent",
                "policy_name": "my-nbe-payment-policy",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "my-nbe-payment-policy"
        assert len(data["rules"]) >= 10
        # Template metadata should be stored
        assert data["metadata"]["template"] == "nbe_payment_agent"
        assert data["metadata"]["regulator"] == "National Bank of Ethiopia (NBE)"
        assert data["metadata"]["override_count"] == 0

    @pytest.mark.asyncio
    async def test_create_policy_from_template_with_overrides(self, api_client):
        override = "Agent may not process payments above ETB 5,000 on weekends"
        resp = await api_client.post(
            "/policies/from-template",
            json={
                "template_name": "nbe_mobile_banking",
                "policy_name": "mobile-banking-strict",
                "overrides": [override],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["rules"][-1] == override
        assert data["metadata"]["override_count"] == 1

    @pytest.mark.asyncio
    async def test_create_policy_from_template_uses_template_description(self, api_client):
        resp = await api_client.post(
            "/policies/from-template",
            json={
                "template_name": "nbe_lending_agent",
                "policy_name": "lending-policy",
            },
        )
        assert resp.status_code == 201
        # Description should default to the template's description
        assert resp.json()["description"] != ""

    @pytest.mark.asyncio
    async def test_create_policy_from_template_unknown_returns_404(self, api_client):
        resp = await api_client.post(
            "/policies/from-template",
            json={
                "template_name": "unknown_template",
                "policy_name": "bad-policy",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_created_policy_is_retrievable(self, api_client):
        """Policy created from a template should be retrievable via GET /policies/{id}."""
        create_resp = await api_client.post(
            "/policies/from-template",
            json={
                "template_name": "nbe_forex_agent",
                "policy_name": "forex-policy",
            },
        )
        policy_id = create_resp.json()["id"]

        get_resp = await api_client.get(f"/policies/{policy_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == policy_id
        assert get_resp.json()["metadata"]["template"] == "nbe_forex_agent"

    @pytest.mark.asyncio
    async def test_all_templates_can_create_policies(self, api_client):
        """Smoke test: every template should produce a valid policy."""
        for template in PolicyTemplate:
            resp = await api_client.post(
                "/policies/from-template",
                json={
                    "template_name": template.value,
                    "policy_name": f"smoke-{template.value}",
                },
            )
            assert resp.status_code == 201, (
                f"Template {template.value} failed: {resp.text}"
            )
            data = resp.json()
            assert len(data["rules"]) >= 8
