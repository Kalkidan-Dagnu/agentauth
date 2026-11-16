# AgentAuth Java SDK

Java SDK for [AgentAuth](https://github.com/Kalkidan-Dagnu/agentauth) — open-source identity and authentication layer for AI agents.

Built by **[Kalkidan Dagnu](https://github.com/Kalkidan-Dagnu)** · Kibrnet PLC · Addis Ababa, Ethiopia

---

## Requirements

- Java 17+
- Maven 3.8+

## Installation

Add to your `pom.xml`:

```xml
<dependency>
    <groupId>io.agentauth</groupId>
    <artifactId>agentauth-sdk</artifactId>
    <version>0.7.0</version>
</dependency>
```

## Quick Start

```java
import io.agentauth.sdk.client.AgentAuthClient;
import io.agentauth.sdk.model.*;

// 1. Create the client (your org API key from POST /orgs/{id}/api-keys)
AgentAuthClient client = new AgentAuthClient(
    "http://localhost:8000",
    "aak_your_api_key_here"
);

// 2. Create a policy from an NBE Ethiopia template — one line, fully compliant
Policy policy = client.policies().createFromTemplate(
    "nbe_payment_agent",
    "telebirr-payment-policy"
);

// 3. Register an agent
Agent agent = client.agents().register(
    "portfolio-rebalancer",
    "user_123",
    List.of("execute"),
    List.of(policy.getId()),
    null
);

// 4. Check permission before every action
if (client.permissions().isAllowed(agent.getId(), "execute_trade", "BTCUSDT")) {
    // Gemini evaluated the policy and returned ALLOW
    executeTrade();
}

// 5. Register a webhook to be notified of ESCALATE decisions
client.webhooks().register(
    agent.getId(),
    "https://yourapp.com/agentauth/webhook"
);

client.close();
```

---

## API

### `AgentAuthClient`

The main entry point. Implements `AutoCloseable`.

```java
// Default 30s timeout
AgentAuthClient client = new AgentAuthClient(baseUrl, apiKey);

// Custom timeout
AgentAuthClient client = new AgentAuthClient(baseUrl, apiKey, Duration.ofSeconds(60));
```

All org-scoped endpoints require an API key (sent as `X-API-Key` header). Get one by calling `POST /orgs/{id}/api-keys` on the server. The `/templates` endpoint is public — pass `null` as the API key to browse templates without auth.

---

### `client.policies()`

| Method | Description |
|--------|-------------|
| `create(name, rules)` | Create a policy with natural language rules |
| `create(name, rules, description, metadata)` | Full variant |
| `get(policyId)` | Fetch a policy by ID string |
| `list()` | List all policies in the org |
| `createFromTemplate(templateName, policyName)` | Create from an NBE/CBN template |
| `createFromTemplate(templateName, policyName, description, overrides)` | With custom override rules appended |

---

### `client.agents()`

| Method | Description |
|--------|-------------|
| `register(name, ownerId)` | Register an agent (minimal) |
| `register(name, ownerId, scopes, policyIds, description)` | Full variant |
| `get(agentId)` | Fetch an agent by UUID |
| `list(ownerId)` | List all agents for an owner in the org |
| `deactivate(agentId)` | Deactivate an agent |

---

### `client.permissions()`

| Method | Description |
|--------|-------------|
| `evaluate(agentId, action, resource)` | Full evaluation — returns `PermissionDecision` |
| `evaluate(agentId, action, resource, context)` | With context map |
| `isAllowed(agentId, action, resource)` | Convenience — returns `boolean` |
| `isAllowed(agentId, action, resource, context)` | With context map |

---

### `client.webhooks()`

| Method | Description |
|--------|-------------|
| `register(agentId, url)` | Register a webhook (default: ESCALATE events only) |
| `register(agentId, url, events, secret)` | With event list and HMAC secret |
| `list(agentId)` | List webhooks for an agent |
| `delete(webhookId)` | Permanently delete a webhook |

---

### `client.templates()`

| Method | Description |
|--------|-------------|
| `list()` | List all 12 templates (7 NBE + 5 CBN) |
| `listByRegulator(regulator)` | Filter by regulator name |
| `listByTag(tag)` | Filter by tag, e.g. `"payment"`, `"nigeria"` |
| `get(templateName)` | Get a template by name |

---

## Available Policy Templates

Templates provide production-ready, regulatory-compliant rule sets in one line.

### NBE Ethiopia (7 templates)

| Template Name | Directive |
|---|---|
| `nbe_payment_agent` | NBE Payment System Directive FIS/01/2023 |
| `nbe_forex_agent` | NBE Foreign Exchange Directive FXD/60/2024 |
| `nbe_lending_agent` | NBE Credit Risk Management SBB/75/2022 |
| `nbe_kyc_agent` | NBE AML/KYC + FATF 40 Recommendations |
| `nbe_audit_agent` | NBE Internal Audit Directive SBB/68/2019 |
| `nbe_mobile_banking` | NBE Mobile and Internet Banking FIS/03/2023 |
| `nbe_insurance_agent` | NBE Insurance Business Directive IBD/19/2011 |

### CBN Nigeria (5 templates)

| Template Name | Directive |
|---|---|
| `cbn_payment_agent` | CBN Payment Systems + NIBSS NIP Rules |
| `cbn_lending_agent` | CBN Credit / Digital Lending Guidelines |
| `cbn_kyc_aml_agent` | CBN AML/CFT/KYC + BVN Tiered KYC |
| `cbn_mobile_money` | CBN Mobile Money Operations Regulations |
| `cbn_insurance_agent` | NAICOM Insurance Act + CBN Consumer Protection |

---

## Model Classes

| Class | Description |
|---|---|
| `Agent` | Registered AI agent |
| `Policy` | Natural language policy |
| `Permission` | Permission request (action + resource + context) |
| `PermissionDecision` | Full evaluation result from Gemini |
| `Webhook` | Webhook registration |
| `Organization` | Tenant organisation |
| `TemplateInfo` | Policy template metadata |
| `DecisionResult` | Enum: `ALLOW`, `DENY`, `ESCALATE` |
| `ConfidenceLevel` | Enum: `HIGH`, `MEDIUM`, `LOW` |
| `AgentScope` | Enum: `READ`, `WRITE`, `EXECUTE`, `ADMIN`, `CUSTOM` |

`PermissionDecision` convenience methods:

```java
decision.isAllowed()           // result == ALLOW
decision.isDenied()            // result == DENY
decision.isEscalate()          // result == ESCALATE
decision.getDecisionResult()   // returns DecisionResult enum
decision.getConfidenceLevel()  // returns ConfidenceLevel enum
```

---

## Error Handling

All SDK methods throw `java.io.IOException` on HTTP errors. The exception message includes the HTTP status code and the response body.

```java
try {
    Agent agent = client.agents().get(agentId);
} catch (IOException e) {
    // e.getMessage() = "HTTP 404: {\"detail\": \"Agent not found\"}"
}
```

---

## Building and Testing

```bash
cd sdk-java
mvn test                   # run all 30 JUnit 5 tests (MockWebServer — no live server needed)
mvn package                # build the jar
mvn package -DskipTests    # build without tests
```

---

## License

MIT
