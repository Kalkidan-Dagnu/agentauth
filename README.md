# AgentAuth

**Open-source identity and authentication layer for AI agents.**
Powered by Google Gemini. Built by [Kibrnet PLC](https://github.com/kibrnet), Addis Ababa, Ethiopia.

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

### Policies

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/policies` | Create a policy with natural language rules |
| `GET` | `/policies` | List all policies |
| `GET` | `/policies/{id}` | Get a policy by ID |

### Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/agents` | Register an AI agent |
| `GET` | `/agents?owner_id=` | List agents by owner |
| `GET` | `/agents/{id}` | Get an agent by ID |
| `POST` | `/agents/{id}/deactivate` | Deactivate an agent |

### Permissions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/agents/{id}/evaluate` | Evaluate a permission request |

Full interactive docs available at `http://localhost:8000/docs` when the server is running.

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
│   │   ├── models.py      # Agent, Policy, Permission, PermissionDecision
│   │   └── store.py       # In-memory agent and policy registry
│   ├── api/
│   │   └── server.py      # FastAPI REST server
│   └── sdk/
│       └── client.py      # Python SDK client
├── tests/
│   ├── test_models.py
│   ├── test_store.py
│   └── test_api.py
├── .env.example
├── pyproject.toml
└── README.md
```

---

## Roadmap

- [ ] Persistent storage (PostgreSQL)
- [ ] JWT-based agent identity tokens
- [ ] Gemma support for on-device / offline evaluation
- [ ] Java SDK
- [ ] Audit log with full decision trail
- [ ] Policy templates for African regulatory contexts (NBE Ethiopia, CBN Nigeria)
- [ ] Multi-tenant support
- [ ] Webhook notifications for ESCALATE decisions

---

## Built in Africa

AgentAuth is built by **Kalkidan Dagnu**, co-founder of [Kibrnet PLC](https://github.com/kibrnet) in Addis Ababa, Ethiopia.

This project is inspired by the work of Bereket Engida (Better Auth) and the broader movement of world-class developer infrastructure being built from Africa.

The goal: give every African AI developer a secure, production-ready identity layer for their agents — so they can focus on building, not on reinventing security from scratch.

---

## License

MIT — free to use, modify, and build on.

---

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

If you're building an AI product in Africa and want to be an early adopter or design partner, open an issue or reach out directly.
