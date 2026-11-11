"""
Tests for AgentAuth v0.6.0 — CBN Nigeria Policy Templates.

Covers:
  - All 5 CBN templates: structure, rule counts, metadata
  - Registry: 12 total templates (7 NBE + 5 CBN)
  - API endpoints: list, get by name, create from template
  - Filtering by regulator and tag
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentauth.db.models import Base
from agentauth.db.session import get_db
from agentauth.templates import PolicyTemplate, registry

# ── Test database ──────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_test_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_test_session_factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


async def _override_get_db():
    async with _test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


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


# ── Registry tests ─────────────────────────────────────────────────────────────

class TestCBNRegistry:
    def test_total_template_count_is_twelve(self):
        """7 NBE + 5 CBN = 12 total templates."""
        assert registry.count == 12

    def test_all_cbn_enum_values_registered(self):
        cbn_members = [
            PolicyTemplate.CBN_PAYMENT_AGENT,
            PolicyTemplate.CBN_LENDING_AGENT,
            PolicyTemplate.CBN_KYC_AGENT,
            PolicyTemplate.CBN_MOBILE_MONEY,
            PolicyTemplate.CBN_INSURANCE_AGENT,
        ]
        for member in cbn_members:
            template = registry.get(member)
            assert template is not None
            assert template.name == member

    def test_get_cbn_by_name(self):
        t = registry.get_by_name("cbn_payment_agent")
        assert t is not None
        assert t.display_name == "CBN Payment Agent"

    def test_list_by_regulator_cbn(self):
        cbn_templates = registry.list_by_regulator("Central Bank of Nigeria (CBN)")
        assert len(cbn_templates) == 4  # 4 templates use CBN regulator (insurance uses NAICOM/CBN)

    def test_list_by_regulator_naicom(self):
        naicom_templates = registry.list_by_regulator("National Insurance Commission (NAICOM) / CBN")
        assert len(naicom_templates) == 1
        assert naicom_templates[0].name == PolicyTemplate.CBN_INSURANCE_AGENT

    def test_list_by_tag_nigeria(self):
        naija_templates = registry.list_by_tag("nigeria")
        assert len(naija_templates) == 5

    def test_list_by_tag_mobile_money(self):
        mm_templates = registry.list_by_tag("mobile money")
        names = [t.name.value for t in mm_templates]
        assert "cbn_mobile_money" in names
        # NBE mobile banking is tagged "mobile banking" not "mobile money"
        assert "nbe_mobile_banking" not in names

    def test_list_by_tag_bvn(self):
        bvn_templates = registry.list_by_tag("bvn")
        assert len(bvn_templates) >= 2  # KYC + payment at minimum

    def test_build_rules_cbn_no_overrides(self):
        rules = registry.build_rules(PolicyTemplate.CBN_LENDING_AGENT)
        base = registry.get(PolicyTemplate.CBN_LENDING_AGENT).rules
        assert rules == base

    def test_build_rules_cbn_with_overrides(self):
        override = "Agent must not approve loans on weekends"
        rules = registry.build_rules(PolicyTemplate.CBN_LENDING_AGENT, overrides=[override])
        assert rules[-1] == override
        assert len(rules) == len(registry.get(PolicyTemplate.CBN_LENDING_AGENT).rules) + 1

    def test_build_rules_does_not_mutate_cbn_template(self):
        original_count = len(registry.get(PolicyTemplate.CBN_MOBILE_MONEY).rules)
        registry.build_rules(
            PolicyTemplate.CBN_MOBILE_MONEY,
            overrides=["extra 1", "extra 2", "extra 3"],
        )
        assert len(registry.get(PolicyTemplate.CBN_MOBILE_MONEY).rules) == original_count


# ── CBN template content tests ────────────────────────────────────────────────

class TestCBNTemplateContent:
    @pytest.mark.parametrize("template_name, min_rules", [
        (PolicyTemplate.CBN_PAYMENT_AGENT,   12),
        (PolicyTemplate.CBN_LENDING_AGENT,   12),
        (PolicyTemplate.CBN_KYC_AGENT,       12),
        (PolicyTemplate.CBN_MOBILE_MONEY,    14),
        (PolicyTemplate.CBN_INSURANCE_AGENT, 10),
    ])
    def test_each_cbn_template_has_minimum_rules(self, template_name, min_rules):
        template = registry.get(template_name)
        assert len(template.rules) >= min_rules, (
            f"{template_name.value} has only {len(template.rules)} rules, expected >= {min_rules}"
        )

    @pytest.mark.parametrize("template_name", [
        PolicyTemplate.CBN_PAYMENT_AGENT,
        PolicyTemplate.CBN_LENDING_AGENT,
        PolicyTemplate.CBN_KYC_AGENT,
        PolicyTemplate.CBN_MOBILE_MONEY,
        PolicyTemplate.CBN_INSURANCE_AGENT,
    ])
    def test_each_cbn_template_has_required_metadata(self, template_name):
        t = registry.get(template_name)
        assert t.display_name
        assert t.description
        assert t.jurisdiction == "Nigeria"
        assert t.version
        assert len(t.tags) > 0
        assert len(t.references) > 0
        assert "nigeria" in [tag.lower() for tag in t.tags]
        assert "cbn" in [tag.lower() for tag in t.tags]

    @pytest.mark.parametrize("template_name", list([
        PolicyTemplate.CBN_PAYMENT_AGENT,
        PolicyTemplate.CBN_LENDING_AGENT,
        PolicyTemplate.CBN_KYC_AGENT,
        PolicyTemplate.CBN_MOBILE_MONEY,
        PolicyTemplate.CBN_INSURANCE_AGENT,
    ]))
    def test_each_cbn_rule_is_non_empty_string(self, template_name):
        t = registry.get(template_name)
        for rule in t.rules:
            assert isinstance(rule, str)
            assert len(rule.strip()) > 10, f"Rule too short: {rule!r}"

    def test_payment_agent_has_nip_reference(self):
        t = registry.get(PolicyTemplate.CBN_PAYMENT_AGENT)
        all_text = " ".join(t.rules).lower()
        assert "nip" in all_text or "nibss" in all_text

    def test_kyc_agent_has_bvn_rule(self):
        t = registry.get(PolicyTemplate.CBN_KYC_AGENT)
        all_text = " ".join(t.rules).lower()
        assert "bvn" in all_text

    def test_kyc_agent_has_tiered_kyc(self):
        t = registry.get(PolicyTemplate.CBN_KYC_AGENT)
        all_text = " ".join(t.rules).lower()
        assert "tier 1" in all_text
        assert "tier 2" in all_text
        assert "tier 3" in all_text

    def test_mobile_money_has_tier_limits(self):
        t = registry.get(PolicyTemplate.CBN_MOBILE_MONEY)
        all_text = " ".join(t.rules).lower()
        assert "tier" in all_text

    def test_mobile_money_has_ussd_rule(self):
        t = registry.get(PolicyTemplate.CBN_MOBILE_MONEY)
        all_text = " ".join(t.rules).lower()
        assert "ussd" in all_text

    def test_mobile_money_has_sim_swap_rule(self):
        t = registry.get(PolicyTemplate.CBN_MOBILE_MONEY)
        all_text = " ".join(t.rules).lower()
        assert "sim-swap" in all_text or "sim swap" in all_text

    def test_lending_agent_has_debt_to_income_rule(self):
        t = registry.get(PolicyTemplate.CBN_LENDING_AGENT)
        all_text = " ".join(t.rules).lower()
        assert "debt-to-income" in all_text or "debt to income" in all_text

    def test_insurance_agent_has_naicom_reference(self):
        t = registry.get(PolicyTemplate.CBN_INSURANCE_AGENT)
        all_refs = " ".join(t.references).lower()
        assert "naicom" in all_refs

    def test_to_dict_has_all_fields_cbn(self):
        t = registry.get(PolicyTemplate.CBN_PAYMENT_AGENT)
        d = t.to_dict()
        for key in ("name", "display_name", "description", "regulator",
                    "jurisdiction", "version", "rules", "tags", "references", "rule_count"):
            assert key in d, f"Missing key: {key}"
        assert d["rule_count"] == len(t.rules)
        assert d["jurisdiction"] == "Nigeria"


# ── API endpoint tests ────────────────────────────────────────────────────────

class TestCBNAPIEndpoints:
    @pytest.mark.asyncio
    async def test_list_templates_returns_twelve(self, api_client):
        resp = await api_client.get("/templates")
        assert resp.status_code == 200
        assert len(resp.json()) == 12

    @pytest.mark.asyncio
    async def test_list_templates_filter_by_nigeria_tag(self, api_client):
        resp = await api_client.get("/templates", params={"tag": "nigeria"})
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()]
        assert len(names) == 5
        for name in names:
            assert name.startswith("cbn_")

    @pytest.mark.asyncio
    async def test_list_templates_filter_cbn_regulator(self, api_client):
        resp = await api_client.get(
            "/templates",
            params={"regulator": "Central Bank of Nigeria (CBN)"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 4

    @pytest.mark.asyncio
    async def test_get_cbn_template_by_name(self, api_client):
        resp = await api_client.get("/templates/cbn_mobile_money")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "cbn_mobile_money"
        assert data["display_name"] == "CBN Mobile Money Agent"
        assert data["jurisdiction"] == "Nigeria"
        assert len(data["rules"]) >= 14

    @pytest.mark.asyncio
    async def test_get_cbn_kyc_template(self, api_client):
        resp = await api_client.get("/templates/cbn_kyc_aml_agent")
        assert resp.status_code == 200
        data = resp.json()
        assert "bvn" in " ".join(data["rules"]).lower()

    @pytest.mark.asyncio
    async def test_get_unknown_cbn_template_404(self, api_client):
        resp = await api_client.get("/templates/cbn_nonexistent")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_all_cbn_templates_can_create_policies(self, api_client):
        """Smoke test: every CBN template should produce a valid policy via the API."""
        cbn_templates = [
            "cbn_payment_agent",
            "cbn_lending_agent",
            "cbn_kyc_aml_agent",
            "cbn_mobile_money",
            "cbn_insurance_agent",
        ]
        for name in cbn_templates:
            resp = await api_client.post(
                "/policies/from-template",
                json={
                    "template_name": name,
                    "policy_name": f"smoke-{name}",
                },
            )
            assert resp.status_code == 201, (
                f"Template {name} failed: {resp.text}"
            )
            data = resp.json()
            assert len(data["rules"]) >= 10
            assert data["metadata"]["template"] == name
            assert data["metadata"]["jurisdiction"] == "Nigeria"

    @pytest.mark.asyncio
    async def test_create_cbn_policy_with_overrides(self, api_client):
        override = "Agent must not process any transaction on public holidays in Nigeria"
        resp = await api_client.post(
            "/policies/from-template",
            json={
                "template_name": "cbn_payment_agent",
                "policy_name": "cbn-payment-strict",
                "overrides": [override],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["rules"][-1] == override
        assert data["metadata"]["override_count"] == 1
