# AgentAuth

> Open-source identity and authentication layer for AI agents — powered by Google Gemini.

Built by **[Kalkidan Dagnu](https://github.com/Kalkidan-Dagnu)** · [Kibrnet PLC](https://github.com/kibrnet) · Addis Ababa, Ethiopia

---

As AI agents proliferate across Africa — in fintech, health, logistics, and more — there is no authentication infrastructure designed for them. Existing tools are built for human users, expensive for African developers, and have no concept of agent-scoped permissions or dynamic policy evaluation.

**AgentAuth** solves this. It lets developers define what AI agents are allowed to do in plain language, then uses Google Gemini to enforce those policies intelligently at runtime — understanding context, nuance, and edge cases that rigid rule engines miss.

```python
from agentauth.sdk.client import AgentAuthClient

client = AgentAuthClient(base_url="http://localhost:8000")

# Define what your agent is allowed to do — in plain English
policy = client.policies.create(
    name="trading-policy",
    rules=[
        "Agent may execute trades only during market hours (09:00-17:00 EAT)",
        "Agent may not execute single trades above $10,000",
        "Agent must only trade verified assets on the approved list",
    ]
)

# Register your agent
agent = client.agents.register(
    name="portfolio-rebalancer",
    owner_id="user_123",
    scopes=["execute"],
    policy_ids=[str(policy.id)],
)

# Before any action — check permission
if client.permissions.is_allowed(agent.id, "execute_trade", "BTCUSDT", {"amount": 500}):
    # Gemini evaluated the policy and said ALLOW
    execute_trade(...)
```

---

## How It Works

```
AI Agent  →  Permission Request  →  AgentAuth  →  Gemini Reasoning  →  ALLOW / DENY / ESCALATE
                                        │
                              Checks natural language
                              policies assigned to
                              the agent
```

Unlike traditional access control (role-based, attribute-based), AgentAuth uses **Gemini to reason** over policies in natural language. This means:

- Policies can express nuanced, context-dependent rules
- No need to enumerate every possible case upfront
- Gemini explains *why* a decision was made
- Edge cases that a rules engine would miss are caught

---

## Quickstart

### 1. Install

```bash
pip install agentauth
```

### 2. Get a Gemini API key

Sign up at [ai.google.dev](https://ai.google.dev) — free tier available.

### 3. Configure

```bash
cp .env.example .env
# Add your GEMINI_API_KEY to .env
```

### 4. Start the server

```bash
agentauth-server
# or
uvicorn agentauth.api.server:app --reload
```

### 5. Integrate

```python
from agentauth.sdk.client import AgentAuthClient

client = AgentAuthClient(base_url="http://localhost:8000")

# Create a policy
policy = client.policies.create(
    name="safe-policy",
    rules=["Agent may only read data, never write or delete"]
)

# Register an agent
agent = client.agents.register(
    name="my-ai-agent",
    owner_id="your-user-id",
    policy_ids=[str(policy.id)],
)

# Check before acting
decision = client.permissions.evaluate(
    agent_id=str(agent.id),
    action="delete_record",
    resource="user_database",
    context={"record_id": 42}
)

print(decision.result)    # DENY
print(decision.reason)    # "Agent is not authorized to delete records per policy"
print(decision.confidence) # HIGH
```

---

## Use Cases

### Fintech — Trading Agents
Prevent trading bots from executing unauthorized trades, operating outside market hours, or exceeding position limits.

### Healthtech — Clinical Assistants
Ensure AI assistants only access patient data they're authorized to see and cannot prescribe without physician approval.

### Enterprise Automation — Workflow Agents
Control what automated agents can access, modify, or delete in production systems.

### Developer Platforms
Provide developers building AI products a drop-in security layer so they don't have to build identity from scratch.

---

## API Reference

### Organisations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/orgs` | Create a new organisation |
| `GET` | `/orgs/{id}` | Get organisation details |
| `POST` | `/orgs/{id}/api-keys` | Issue an API key for an org |
| `GET` | `/orgs/{id}/api-keys` | List API keys for an org |

### Policies

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/policies` | Create a policy with natural language rules |
| `GET` | `/policies` | List all policies (org-scoped) |
| `GET` | `/policies/{id}` | Get a policy by ID |
| `POST` | `/policies/from-template` | Create a policy from an NBE/CBN template |

### Templates

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/templates` | List all available policy templates |
| `GET` | `/templates/{name}` | Get a specific template by name |

### Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/agents` | Register an AI agent |
| `GET` | `/agents?owner_id=` | List agents by owner |
| `GET` | `/agents/{id}` | Get an agent by ID |
| `POST` | `/agents/{id}/deactivate` | Deactivate an agent |
| `POST` | `/agents/{id}/token` | Issue a signed JWT for an agent |

### Permissions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/agents/{id}/evaluate` | Evaluate a permission request |

### Audit Log

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/agents/{id}/audit` | Query decision history for an agent |

### Webhooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/agents/{id}/webhooks` | Register a webhook for an agent |
| `GET` | `/agents/{id}/webhooks` | List webhooks for an agent |
| `DELETE` | `/webhooks/{id}` | Delete a webhook |
| `GET` | `/webhooks/{id}/deliveries` | Inspect delivery history |

All endpoints except `/health`, `/templates`, and `/orgs` (POST) require an `X-API-Key` header for org authentication.

---

## Permission Decision

Every evaluation returns a `PermissionDecision`:

```json
{
  "request_id": "uuid",
  "agent_id": "uuid",
  "permission": {
    "action": "execute_trade",
    "resource": "binance_spot",
    "context": { "amount": 15000 }
  },
  "result": "DENY",
  "reason": "Trade amount of $15,000 exceeds the maximum single trade limit of $10,000 per policy rule 2.",
  "confidence": "HIGH",
  "matched_rules": [
    "Agent may not execute single trades above $10,000"
  ],
  "evaluated_at": "2026-07-10T10:30:00Z",
  "latency_ms": 342.5
}
```

---

## Running Tests

```bash
pip install "agentauth[dev]"
pytest tests/ -v
```

---

## Project Structure

```
agentauth/
├── agentauth/
│   ├── core/
│   │   ├── engine.py      # Gemini permission reasoning engine
│   │   └── models.py      # Agent, Policy, Permission, PermissionDecision, Webhook, Organization
│   ├── api/
│   │   ├── server.py      # FastAPI REST server (v0.5.0)
│   │   ├── auth.py        # JWT agent identity tokens
│   │   └── tenancy.py     # Multi-tenant API key auth
│   ├── db/
│   │   ├── models.py      # SQLAlchemy ORM models
│   │   ├── session.py     # Async DB session + engine setup
│   │   └── stores.py      # DB-backed stores (agents, policies, webhooks, audit, orgs)
│   ├── sdk/
│   │   └── client.py      # Python SDK client
│   ├── templates/
│   │   ├── registry.py    # Template registry + PolicyTemplate enum
│   │   ├── nbe.py         # NBE Ethiopia templates (7 templates)
│   │   └── cbn.py         # CBN Nigeria templates (5 templates)
│   └── webhooks/
│       └── dispatcher.py  # Webhook delivery with retry + backoff
├── alembic/
│   └── versions/         # Database migrations
├── tests/
│   ├── test_models.py
│   ├── test_store.py
│   ├── test_api.py
│   ├── test_auth.py
│   ├── test_webhooks.py
│   ├── test_templates.py
│   ├── test_cbn_templates.py
│   └── test_tenancy.py
├── .env.example
├── pyproject.toml
└── README.md
```

---

## Roadmap

- [x] Persistent storage (PostgreSQL)
- [x] JWT-based agent identity tokens
- [x] Audit log with full decision trail
- [x] Webhook notifications for ESCALATE decisions
- [x] Policy templates for African regulatory contexts (NBE Ethiopia, CBN Nigeria)
- [x] Multi-tenant support
- [ ] Gemma support for on-device / offline evaluation
- [ ] Java SDK

---

## Built in Africa

AgentAuth is built by **Kalkidan Dagnu**, co-founder of [Kibrnet PLC](https://github.com/kibrnet) in Addis Ababa, Ethiopia.

This project is part of the broader movement of world-class developer infrastructure being built from Africa.

The goal: give every African AI developer a secure, production-ready identity layer for their agents — so they can focus on building, not on reinventing security from scratch.

---

## License

MIT — free to use, modify, and build on.

---

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

If you're building an AI product in Africa and want to be an early adopter or design partner, open an issue or reach out directly.
