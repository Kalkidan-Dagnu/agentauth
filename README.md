# AgentAuth

[![CI](https://github.com/Kalkidan-Dagnu/agentauth/actions/workflows/ci.yml/badge.svg)](https://github.com/Kalkidan-Dagnu/agentauth/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agentauth)](https://pypi.org/project/agentauth/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![Java](https://img.shields.io/badge/Java%20SDK-17%2B-orange)](sdk-java/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Live API](https://img.shields.io/badge/Live%20API-agentauth.fly.dev-brightgreen)](https://agentauth.fly.dev/docs)

**Identity and permission layer for AI agents — in plain English.**

AI agents need to be told what they're allowed to do. AgentAuth lets you define those rules in natural language, then uses an LLM reasoning engine (Google Gemini or local Gemma) to enforce them at runtime — with a full audit trail, multi-tenancy, webhooks, and Python and Java SDKs.

**[→ Live API Docs](https://agentauth.fly.dev/docs)** · **[→ Python SDK](#python-sdk)** · **[→ Java SDK](sdk-java/README.md)**

---

## Demo

```python
from agentauth.sdk.client import AgentAuthClient

client = AgentAuthClient(base_url="https://agentauth.fly.dev")

# 1. Create a policy in plain English
policy = client.policies.create(
    name="trading-limits",
    rules=[
        "Agent may execute trades only during market hours (09:00–17:00 EAT)",
        "Agent may not execute single trades above $10,000",
        "Agent must only trade assets on the approved list",
    ]
)

# 2. Register your agent
agent = client.agents.register(
    name="portfolio-rebalancer",
    owner_id="user_123",
    policy_ids=[str(policy.id)],
)

# 3. Check before every action — Gemini reasons against your policies
decision = client.permissions.evaluate(
    agent_id=str(agent.id),
    action="execute_trade",
    resource="BTCUSDT",
    context={"amount": 15000}
)

print(decision.result)    # DENY
print(decision.reason)    # "Trade amount of $15,000 exceeds the $10,000 limit per rule 2."
print(decision.confidence) # HIGH
```

> **[→ Try it on the live server](https://agentauth.fly.dev/docs)**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your Application                         │
│                                                                 │
│   AI Agent  ──► AgentAuth SDK  ──► POST /agents/{id}/evaluate  │
└──────────────────────────────────────┬──────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                       AgentAuth Server                          │
│                                                                 │
│  ┌──────────────┐    ┌─────────────────┐    ┌───────────────┐  │
│  │  API Layer   │    │ Reasoning Engine │    │  Audit Store  │  │
│  │  (FastAPI)   │───►│                 │───►│  (PostgreSQL) │  │
│  │  Multi-tenant│    │  BaseEngine ABC │    └───────────────┘  │
│  │  JWT + APIKey│    │      │      │   │                        │
│  └──────────────┘    │   Gemini  Gemma │    ┌───────────────┐  │
│                      │  (cloud) (local)│    │   Webhooks    │  │
│                      └─────────────────┘    │  (HMAC-signed)│  │
│                                             └───────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
     Python SDK                  Java SDK              REST API
  (agentauth.sdk)              (sdk-java/)        (any language)
```

**Decision flow:**

```
Agent Action  →  evaluate(action, resource, context)
                        │
              Load agent + policies from DB
                        │
              Build reasoning prompt
                        │
              ┌─────────▼─────────┐
              │   Gemini / Gemma   │  ← switchable via REASONING_BACKEND env var
              └─────────┬─────────┘
                        │
              Parse JSON response
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
       ALLOW          DENY         ESCALATE
         │              │              │
         └──────────────┴──────────────┘
                        │
              Persist to audit log
              Fire webhooks (if ESCALATE)
                        │
              Return PermissionDecision
```

---

## Why This Exists

Existing IAM tools (AWS IAM, Auth0, Keycloak) were built for human users. They model permissions as static role memberships and boolean flags.

AI agents need something different:
- **Context-dependent rules** — "only trade during market hours" is not a boolean
- **Natural language policies** — written by product and compliance teams, not engineers
- **Explainability** — agents need to know *why* a request was denied, not just that it was
- **Offline operation** — regulated environments cannot send every decision to a cloud API

AgentAuth addresses all four. It's the security layer you'd have to build yourself otherwise.

---

## Features

| Feature | Status |
|---|---|
| Natural language policy evaluation (Gemini) | ✅ |
| Offline evaluation (Gemma via HuggingFace) | ✅ |
| Multi-tenant org isolation | ✅ |
| SHA-256 hashed API key auth | ✅ |
| JWT agent identity tokens | ✅ |
| Full audit log with decision trail | ✅ |
| HMAC-signed webhook delivery + retry backoff | ✅ |
| Regulatory compliance templates (NBE Ethiopia, CBN Nigeria) | ✅ 12 templates, 179 rules |
| Python SDK | ✅ |
| Java SDK (MockWebServer, 27 tests) | ✅ |
| Alembic migration chain | ✅ |
| Deployed on Fly.io | ✅ |

---

## Quickstart

### 1. Install

```bash
pip install agentauth
```

### 2. Start the server

```bash
cp .env.example .env
# Add GEMINI_API_KEY and DATABASE_URL to .env
agentauth-server
```

To use Gemma instead (fully offline, no API key needed):

```bash
REASONING_BACKEND=gemma GEMMA_MODEL_ID=google/gemma-2-2b-it agentauth-server
```

### 3. Create an org and get an API key

```python
from agentauth.sdk.client import AgentAuthClient

client = AgentAuthClient(base_url="http://localhost:8000")

org = client.orgs.create(name="my-company", slug="my-company", owner_id="user_1")
key = client.orgs.issue_api_key(org_id=str(org.id), name="production")

# Use key.plaintext_key as your X-API-Key header going forward
client = AgentAuthClient(base_url="http://localhost:8000", api_key=key.plaintext_key)
```

### 4. Use a compliance template (optional)

```python
# Apply 179 pre-built NBE / CBN regulatory rules in one line
policy = client.policies.create_from_template(
    template_name="nbe_payment_agent",
    policy_name="NBE Payment Rules",
)
```

---

## Python SDK

```python
from agentauth.sdk.client import AgentAuthClient

client = AgentAuthClient(base_url="http://localhost:8000", api_key="your-key")

# Policies
policy = client.policies.create(name="my-policy", rules=["Agent may only read data"])
policies = client.policies.list()

# Agents
agent = client.agents.register(name="reader-bot", owner_id="u1", policy_ids=[str(policy.id)])
token = client.agents.issue_token(agent_id=str(agent.id))

# Permissions
decision = client.permissions.evaluate(
    agent_id=str(agent.id), action="delete_record", resource="users", context={"id": 42}
)
# decision.result → DENY
# decision.reason → "Agent is not authorized to delete records per policy rule 1."

# Audit
history = client.audit.list(agent_id=str(agent.id))
```

---

## Java SDK

```java
AgentAuthClient client = new AgentAuthClient("http://localhost:8000", "your-api-key");

// Register agent
AgentResponse agent = client.registerAgent("my-agent", "user_1", List.of(policyId));

// Evaluate
PermissionDecision decision = client.evaluatePermission(
    agent.getId(), "execute_trade", "binance", Map.of("amount", 500)
);

System.out.println(decision.getResult());    // ALLOW
System.out.println(decision.getReason());
```

See [sdk-java/README.md](sdk-java/README.md) for the full Java reference.

---

## Permission Decision

Every evaluation returns:

```json
{
  "request_id": "uuid",
  "agent_id": "uuid",
  "permission": {
    "action": "execute_trade",
    "resource": "BTCUSDT",
    "context": { "amount": 15000 }
  },
  "result": "DENY",
  "reason": "Trade amount of $15,000 exceeds the maximum single trade limit of $10,000 per rule 2.",
  "confidence": "HIGH",
  "matched_rules": [
    "Agent may not execute single trades above $10,000"
  ],
  "evaluated_at": "2026-11-23T10:00:00Z",
  "latency_ms": 342.5
}
```

---

## Compliance Templates

AgentAuth ships 12 regulatory policy templates covering African financial regulations:

| Template | Regulator | Rules |
|---|---|---|
| `nbe_payment_agent` | NBE Ethiopia | Payment processing limits, AML, KYC |
| `nbe_lending_agent` | NBE Ethiopia | Credit scoring, loan disbursement controls |
| `nbe_forex_agent` | NBE Ethiopia | Foreign currency trading restrictions |
| `nbe_audit_agent` | NBE Ethiopia | Audit and reporting obligations |
| `nbe_kyc_agent` | NBE Ethiopia | Customer identity verification |
| `nbe_risk_agent` | NBE Ethiopia | Risk assessment and monitoring |
| `nbe_data_agent` | NBE Ethiopia | Data residency and privacy |
| `cbn_payment_agent` | CBN Nigeria | Payment authorization controls |
| `cbn_lending_agent` | CBN Nigeria | Lending and credit restrictions |
| `cbn_forex_agent` | CBN Nigeria | FX and remittance rules |
| `cbn_kyc_agent` | CBN Nigeria | KYC and AML requirements |
| `cbn_risk_agent` | CBN Nigeria | Risk and capital adequacy |

```bash
GET /templates                    # list all
GET /templates/nbe_payment_agent  # inspect rules
POST /policies/from-template      # apply in one call
```

---

## API Reference

### Organisations
| Method | Endpoint | Auth |
|---|---|---|
| `POST` | `/orgs` | None |
| `GET` | `/orgs/{id}` | API key |
| `POST` | `/orgs/{id}/api-keys` | API key |
| `GET` | `/orgs/{id}/api-keys` | API key |

### Agents
| Method | Endpoint |
|---|---|
| `POST` | `/agents` |
| `GET` | `/agents?owner_id=` |
| `GET` | `/agents/{id}` |
| `POST` | `/agents/{id}/deactivate` |
| `POST` | `/agents/{id}/token` |

### Policies & Templates
| Method | Endpoint |
|---|---|
| `POST` | `/policies` |
| `GET` | `/policies` |
| `GET` | `/policies/{id}` |
| `POST` | `/policies/from-template` |
| `GET` | `/templates` |
| `GET` | `/templates/{name}` |

### Permissions & Audit
| Method | Endpoint |
|---|---|
| `POST` | `/agents/{id}/evaluate` |
| `GET` | `/agents/{id}/audit` |

### Webhooks
| Method | Endpoint |
|---|---|
| `POST` | `/agents/{id}/webhooks` |
| `GET` | `/agents/{id}/webhooks` |
| `DELETE` | `/webhooks/{id}` |
| `GET` | `/webhooks/{id}/deliveries` |

All endpoints except `/health`, `/templates` (GET), and `/orgs` (POST) require `X-API-Key`.

---

## Project Structure

```
agentauth/
├── agentauth/
│   ├── core/
│   │   ├── base_engine.py    # Abstract BaseEngine — Gemini and Gemma share this interface
│   │   ├── engine.py         # Gemini backend
│   │   ├── gemma_engine.py   # Gemma backend (local, offline)
│   │   └── models.py         # Domain models: Agent, Policy, Permission, PermissionDecision
│   ├── api/
│   │   ├── server.py         # FastAPI app — all routes, v0.8.0
│   │   ├── auth.py           # JWT agent identity tokens
│   │   └── tenancy.py        # Multi-tenant API key authentication
│   ├── db/
│   │   ├── models.py         # SQLAlchemy ORM models
│   │   ├── session.py        # Async DB session factory
│   │   └── stores.py         # Data access layer
│   ├── sdk/
│   │   └── client.py         # Python SDK
│   ├── templates/
│   │   ├── registry.py       # Template registry
│   │   ├── nbe.py            # NBE Ethiopia: 7 templates, 100+ rules
│   │   └── cbn.py            # CBN Nigeria: 5 templates, 79 rules
│   └── webhooks/
│       └── dispatcher.py     # HMAC-signed delivery with retry + exponential backoff
├── sdk-java/                 # Java SDK (Maven, 27 tests with MockWebServer)
├── alembic/versions/         # 3 migrations: initial → webhooks → multi-tenant
├── tests/                    # 100+ tests across 8 test files
├── .github/workflows/ci.yml  # CI: Python tests + Java SDK tests
├── .env.example
└── pyproject.toml
```

---

## Running Tests

```bash
# Python
pip install -e ".[dev]"
pytest tests/ -v

# Java SDK
cd sdk-java && mvn test
```

---

## Roadmap

- [x] Natural language policy evaluation (Gemini)
- [x] Persistent storage (PostgreSQL + Alembic migrations)
- [x] JWT agent identity tokens
- [x] Full audit log
- [x] HMAC-signed webhook delivery with retry backoff
- [x] Regulatory compliance templates (NBE Ethiopia, CBN Nigeria — 12 templates, 179 rules)
- [x] Multi-tenant org isolation
- [x] Offline evaluation backend (Gemma via HuggingFace Transformers)
- [x] Java SDK (27 tests, MockWebServer)
- [ ] TypeScript / Node.js SDK
- [ ] Rate limiting and quota enforcement per org
- [ ] Dashboard UI

---

## Built in Africa

**Kalkidan Dagnu**, Senior Software Engineer, [Kibrnet PLC](https://github.com/kibrnet) — Addis Ababa, Ethiopia.

The goal: give every African AI developer a secure, production-ready identity layer for their agents — so they can build products, not security infrastructure.

---

## License

MIT — free to use, modify, and build on.

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
