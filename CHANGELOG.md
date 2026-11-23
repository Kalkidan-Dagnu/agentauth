# Changelog

All notable changes to AgentAuth are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [0.8.0] — 2026-11-16

### Added
- **Gemma offline backend** (`GemmaEngine`) — run policy evaluation entirely locally via HuggingFace Transformers, with no external API dependency. Switch with `REASONING_BACKEND=gemma`.
- `BaseEngine` abstract class — both Gemini and Gemma now share the same prompt template, JSON parsing, error handling, and audit logging. Backends are interchangeable.
- `GEMMA_MODEL_ID`, `GEMMA_MODEL_PATH`, `GEMMA_LOAD_IN_4BIT`, `GEMMA_LOAD_IN_8BIT` environment variables for Gemma configuration.
- Optional `agentauth[gemma]` install extra (`transformers`, `torch`, `accelerate`).
- Full test suite for `GemmaEngine` and `BaseEngine` (`tests/test_gemma_engine.py`).

### Changed
- Server version bumped to `0.8.0` in `server.py` and `pyproject.toml`.
- CI workflow updated to run Gemma engine tests in the Python test job.

---

## [0.7.0] — 2026-11-16

### Added
- **Java SDK** (`sdk-java/`) — full Maven project with 27 tests using `MockWebServer`. Covers all core operations: org management, agent registration, policy CRUD, permission evaluation, audit log, webhooks.
- `sdk-java/README.md` — Java quickstart, Maven coordinates, full API reference.

---

## [0.6.0] — 2026-11-11

### Added
- **CBN Nigeria compliance templates** (`agentauth/templates/cbn.py`) — 5 templates covering payment, lending, forex, KYC, and risk management.
- `test_cbn_templates.py` — test coverage for all CBN templates.
- Template registry now supports filtering by `regulator` and `tag` via `GET /templates?regulator=CBN`.

### Changed
- Total compliance template count: 12 templates, 179 rules (up from 7 / 100+).

---

## [0.5.0] — 2026-11-11

### Added
- **Multi-tenant support** — all resources (agents, policies, webhooks, audit log) are scoped to an `Organization`. Orgs are isolated by hashed API key.
- `POST /orgs` — create a new tenant organisation (no auth required).
- `POST /orgs/{id}/api-keys` — issue named API keys per org.
- `GET /orgs/{id}/api-keys` — list API key metadata (plaintext never stored).
- Alembic migration `0003_multi_tenant.py` — adds `org_id` foreign key to all resource tables.
- `test_tenancy.py` — integration tests for org isolation, API key issuance, and cross-org access prevention.

### Changed
- All agent, policy, webhook, and audit endpoints now require `X-API-Key` header.
- Stores updated to accept `org_id` parameter for all queries.

---

## [0.4.0] — 2026-11-11

### Added
- **NBE Ethiopia compliance templates** (`agentauth/templates/nbe.py`) — 7 templates covering payment agents, lending, forex, audit, KYC, risk, and data handling.
- Template registry (`agentauth/templates/registry.py`) — `list_all()`, `get_by_name()`, `list_by_regulator()`, `list_by_tag()`, `build_rules()`.
- `POST /policies/from-template` — create a policy from a template in one API call, with optional rule overrides.
- `GET /templates` and `GET /templates/{name}` endpoints (no auth — open to all).
- `test_templates.py` — 30+ tests for template retrieval, rule building, and policy creation.

---

## [0.3.0] — 2026-11-11

### Added
- **Webhooks** — register HTTPS endpoints to receive signed payloads on `ESCALATE` decisions (or any event type).
- HMAC-SHA256 request signing — receivers can verify payload authenticity via `X-AgentAuth-Signature` header.
- Exponential backoff retry — up to 3 delivery attempts with 2×, 4×, 8× delay.
- Delivery history — full log of attempts, status codes, and response bodies per webhook.
- `POST /agents/{id}/webhooks`, `GET /agents/{id}/webhooks`, `DELETE /webhooks/{id}`, `GET /webhooks/{id}/deliveries`.
- Alembic migration `0002_webhooks.py`.
- `test_webhooks.py` — 25+ tests covering registration, delivery, signing verification, retry logic.

---

## [0.2.0] — 2026-11-11

### Added
- **JWT agent identity tokens** — `POST /agents/{id}/token` issues a signed JWT. Agents can authenticate subsequent requests using `Authorization: Bearer <token>`.
- Token validation on `POST /agents/{id}/evaluate` — optional bearer token validated against `agent_id` in the path, preventing cross-agent impersonation.
- `test_auth.py` — token issuance and validation tests.

---

## [0.1.0] — 2026-11-10

### Added
- Initial release.
- FastAPI server with Gemini-powered permission evaluation.
- `Agent`, `Policy`, `Permission`, `PermissionDecision` domain models.
- `POST /agents`, `GET /agents`, `GET /agents/{id}`, `POST /agents/{id}/deactivate`.
- `POST /policies`, `GET /policies`, `GET /policies/{id}`.
- `POST /agents/{id}/evaluate` — returns `ALLOW`, `DENY`, or `ESCALATE` with reason, confidence, and matched rules.
- `GET /agents/{id}/audit` — paginated audit log.
- PostgreSQL persistence via SQLAlchemy async ORM.
- Alembic migration chain starting at `0001_initial.py`.
- Python SDK (`agentauth.sdk.client.AgentAuthClient`).
- Deployed to Fly.io at `agentauth.fly.dev`.
- MIT license.
