package io.agentauth.sdk;

import io.agentauth.sdk.client.AgentAuthClient;
import io.agentauth.sdk.model.*;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.*;

import java.io.IOException;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Tests for the AgentAuth Java SDK using MockWebServer.
 *
 * Every test spins up a local HTTP server, stubs the expected response,
 * makes the SDK call, and asserts both the return value and the outgoing
 * request shape (path, method, headers, body).
 */
class AgentAuthClientTest {

    private MockWebServer server;
    private AgentAuthClient client;

    static final String API_KEY = "aak_test1234567890abcdef12345678";

    // ── Shared JSON fixtures ──────────────────────────────────────────────────

    static final String POLICY_JSON = """
            {
              "id": "00000000-0000-0000-0000-000000000001",
              "name": "test-policy",
              "description": "A test policy",
              "rules": ["Allow all reads", "Deny deletes"],
              "metadata": {},
              "created_at": "2026-11-11T10:00:00",
              "updated_at": "2026-11-11T10:00:00"
            }
            """;

    static final String AGENT_JSON = """
            {
              "id": "00000000-0000-0000-0000-000000000002",
              "name": "test-agent",
              "owner_id": "user_1",
              "scopes": ["read"],
              "policy_ids": [],
              "is_active": true,
              "created_at": "2026-11-11T10:00:00",
              "metadata": {}
            }
            """;

    static final String DECISION_ALLOW_JSON = """
            {
              "request_id": "00000000-0000-0000-0000-000000000003",
              "agent_id": "00000000-0000-0000-0000-000000000002",
              "permission": {"action": "read", "resource": "database", "context": {}},
              "result": "ALLOW",
              "reason": "Policy allows reads",
              "confidence": "HIGH",
              "matched_rules": ["Allow all reads"],
              "evaluated_at": "2026-11-11T10:00:00",
              "latency_ms": 123.4
            }
            """;

    static final String DECISION_DENY_JSON = """
            {
              "request_id": "00000000-0000-0000-0000-000000000004",
              "agent_id": "00000000-0000-0000-0000-000000000002",
              "permission": {"action": "delete", "resource": "database", "context": {}},
              "result": "DENY",
              "reason": "Policy denies deletes",
              "confidence": "HIGH",
              "matched_rules": ["Deny deletes"],
              "evaluated_at": "2026-11-11T10:00:00",
              "latency_ms": 98.0
            }
            """;

    static final String WEBHOOK_JSON = """
            {
              "id": "00000000-0000-0000-0000-000000000005",
              "agent_id": "00000000-0000-0000-0000-000000000002",
              "url": "https://example.com/hook",
              "events": ["ESCALATE"],
              "is_active": true,
              "created_at": "2026-11-11T10:00:00"
            }
            """;

    static final String TEMPLATE_JSON = """
            {
              "name": "nbe_payment_agent",
              "display_name": "NBE Payment Agent",
              "description": "Governs AI agents processing payments under NBE directives.",
              "regulator": "National Bank of Ethiopia (NBE)",
              "jurisdiction": "Ethiopia",
              "version": "1.0.0",
              "rules": ["Agent may not exceed ETB 200,000 per transaction"],
              "tags": ["payment", "ethiopia", "nbe"],
              "references": ["NBE Payment System Directive FIS/01/2023"],
              "rule_count": 1
            }
            """;

    // ── Setup / teardown ──────────────────────────────────────────────────────

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();
        client = new AgentAuthClient(server.url("/").toString(), API_KEY);
    }

    @AfterEach
    void tearDown() throws IOException {
        client.close();
        server.shutdown();
    }

    // ── Health ────────────────────────────────────────────────────────────────

    @Test
    void health_returnsJson() throws Exception {
        server.enqueue(new MockResponse()
                .setBody("{\"status\":\"healthy\",\"version\":\"0.7.0\"}")
                .addHeader("Content-Type", "application/json"));

        String result = client.health();
        assertTrue(result.contains("healthy"));

        RecordedRequest req = server.takeRequest();
        assertEquals("/health", req.getPath());
        assertEquals("GET", req.getMethod());
    }

    // ── Policies ─────────────────────────────────────────────────────────────

    @Test
    void policies_create_sendsCorrectRequestAndReturnsPolicy() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(201)
                .setBody(POLICY_JSON)
                .addHeader("Content-Type", "application/json"));

        Policy policy = client.policies().create(
                "test-policy",
                List.of("Allow all reads", "Deny deletes")
        );

        assertNotNull(policy.getId());
        assertEquals("test-policy", policy.getName());
        assertEquals(2, policy.getRules().size());

        RecordedRequest req = server.takeRequest();
        assertEquals("/policies", req.getPath());
        assertEquals("POST", req.getMethod());
        assertEquals(API_KEY, req.getHeader("X-API-Key"));
        String body = req.getBody().readUtf8();
        assertTrue(body.contains("test-policy"));
        assertTrue(body.contains("Allow all reads"));
    }

    @Test
    void policies_get_returnsPolicy() throws Exception {
        server.enqueue(new MockResponse()
                .setBody(POLICY_JSON)
                .addHeader("Content-Type", "application/json"));

        Policy policy = client.policies().get("00000000-0000-0000-0000-000000000001");
        assertEquals("test-policy", policy.getName());

        RecordedRequest req = server.takeRequest();
        assertEquals("/policies/00000000-0000-0000-0000-000000000001", req.getPath());
        assertEquals("GET", req.getMethod());
    }

    @Test
    void policies_list_returnsListOfPolicies() throws Exception {
        server.enqueue(new MockResponse()
                .setBody("[" + POLICY_JSON + "]")
                .addHeader("Content-Type", "application/json"));

        List<Policy> policies = client.policies().list();
        assertEquals(1, policies.size());
        assertEquals("test-policy", policies.get(0).getName());

        RecordedRequest req = server.takeRequest();
        assertEquals("/policies", req.getPath());
        assertEquals("GET", req.getMethod());
    }

    @Test
    void policies_createFromTemplate_sendsTemplateNameAndReturnsPolicy() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(201)
                .setBody(POLICY_JSON)
                .addHeader("Content-Type", "application/json"));

        Policy policy = client.policies().createFromTemplate(
                "nbe_payment_agent",
                "my-payment-policy"
        );

        assertNotNull(policy);

        RecordedRequest req = server.takeRequest();
        assertEquals("/policies/from-template", req.getPath());
        assertEquals("POST", req.getMethod());
        String body = req.getBody().readUtf8();
        assertTrue(body.contains("nbe_payment_agent"));
        assertTrue(body.contains("my-payment-policy"));
    }

    @Test
    void policies_createFromTemplate_withOverrides_sendsOverrides() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(201)
                .setBody(POLICY_JSON)
                .addHeader("Content-Type", "application/json"));

        client.policies().createFromTemplate(
                "cbn_mobile_money",
                "strict-mobile-policy",
                null,
                List.of("Agent must not process above NGN 10,000 on weekends")
        );

        RecordedRequest req = server.takeRequest();
        String body = req.getBody().readUtf8();
        assertTrue(body.contains("cbn_mobile_money"));
        assertTrue(body.contains("NGN 10,000"));
    }

    // ── Agents ───────────────────────────────────────────────────────────────

    @Test
    void agents_register_sendsCorrectRequestAndReturnsAgent() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(201)
                .setBody(AGENT_JSON)
                .addHeader("Content-Type", "application/json"));

        Agent agent = client.agents().register("test-agent", "user_1");

        assertNotNull(agent.getId());
        assertEquals("test-agent", agent.getName());
        assertEquals("user_1", agent.getOwnerId());
        assertTrue(agent.isActive());

        RecordedRequest req = server.takeRequest();
        assertEquals("/agents", req.getPath());
        assertEquals("POST", req.getMethod());
        assertEquals(API_KEY, req.getHeader("X-API-Key"));
    }

    @Test
    void agents_get_returnsAgent() throws Exception {
        UUID agentId = UUID.fromString("00000000-0000-0000-0000-000000000002");
        server.enqueue(new MockResponse()
                .setBody(AGENT_JSON)
                .addHeader("Content-Type", "application/json"));

        Agent agent = client.agents().get(agentId);
        assertEquals(agentId, agent.getId());

        RecordedRequest req = server.takeRequest();
        assertEquals("/agents/" + agentId, req.getPath());
    }

    @Test
    void agents_list_returnsListOfAgents() throws Exception {
        server.enqueue(new MockResponse()
                .setBody("[" + AGENT_JSON + "]")
                .addHeader("Content-Type", "application/json"));

        List<Agent> agents = client.agents().list("user_1");
        assertEquals(1, agents.size());
        assertEquals("test-agent", agents.get(0).getName());

        RecordedRequest req = server.takeRequest();
        assertTrue(req.getPath().contains("/agents"));
        assertTrue(req.getPath().contains("owner_id=user_1"));
    }

    @Test
    void agents_deactivate_returnsTrue() throws Exception {
        UUID agentId = UUID.fromString("00000000-0000-0000-0000-000000000002");
        server.enqueue(new MockResponse()
                .setBody("{\"success\": true}")
                .addHeader("Content-Type", "application/json"));

        boolean result = client.agents().deactivate(agentId);
        assertTrue(result);

        RecordedRequest req = server.takeRequest();
        assertEquals("/agents/" + agentId + "/deactivate", req.getPath());
        assertEquals("POST", req.getMethod());
    }

    // ── Permission Evaluation ─────────────────────────────────────────────────

    @Test
    void permissions_evaluate_allowDecision() throws Exception {
        UUID agentId = UUID.fromString("00000000-0000-0000-0000-000000000002");
        server.enqueue(new MockResponse()
                .setBody(DECISION_ALLOW_JSON)
                .addHeader("Content-Type", "application/json"));

        PermissionDecision decision = client.permissions().evaluate(agentId, "read", "database");

        assertEquals("ALLOW", decision.getResult());
        assertEquals(DecisionResult.ALLOW, decision.getDecisionResult());
        assertTrue(decision.isAllowed());
        assertFalse(decision.isDenied());
        assertFalse(decision.isEscalate());
        assertEquals(ConfidenceLevel.HIGH, decision.getConfidenceLevel());
        assertNotNull(decision.getReason());
        assertFalse(decision.getMatchedRules().isEmpty());

        RecordedRequest req = server.takeRequest();
        assertEquals("/agents/" + agentId + "/evaluate", req.getPath());
        assertEquals("POST", req.getMethod());
        String body = req.getBody().readUtf8();
        assertTrue(body.contains("\"action\":\"read\""));
        assertTrue(body.contains("\"resource\":\"database\""));
    }

    @Test
    void permissions_evaluate_denyDecision() throws Exception {
        UUID agentId = UUID.fromString("00000000-0000-0000-0000-000000000002");
        server.enqueue(new MockResponse()
                .setBody(DECISION_DENY_JSON)
                .addHeader("Content-Type", "application/json"));

        PermissionDecision decision = client.permissions().evaluate(agentId, "delete", "database");

        assertEquals("DENY", decision.getResult());
        assertFalse(decision.isAllowed());
        assertTrue(decision.isDenied());
    }

    @Test
    void permissions_isAllowed_returnsTrue_forAllowDecision() throws Exception {
        UUID agentId = UUID.fromString("00000000-0000-0000-0000-000000000002");
        server.enqueue(new MockResponse()
                .setBody(DECISION_ALLOW_JSON)
                .addHeader("Content-Type", "application/json"));

        assertTrue(client.permissions().isAllowed(agentId, "read", "database"));
    }

    @Test
    void permissions_isAllowed_returnsFalse_forDenyDecision() throws Exception {
        UUID agentId = UUID.fromString("00000000-0000-0000-0000-000000000002");
        server.enqueue(new MockResponse()
                .setBody(DECISION_DENY_JSON)
                .addHeader("Content-Type", "application/json"));

        assertFalse(client.permissions().isAllowed(agentId, "delete", "database"));
    }

    @Test
    void permissions_evaluate_includesContextInRequest() throws Exception {
        UUID agentId = UUID.fromString("00000000-0000-0000-0000-000000000002");
        server.enqueue(new MockResponse()
                .setBody(DECISION_ALLOW_JSON)
                .addHeader("Content-Type", "application/json"));

        client.permissions().evaluate(
                agentId, "transfer", "wallet",
                java.util.Map.of("amount", 500, "currency", "ETB")
        );

        RecordedRequest req = server.takeRequest();
        String body = req.getBody().readUtf8();
        assertTrue(body.contains("\"context\""));
        assertTrue(body.contains("amount"));
    }

    // ── Webhooks ─────────────────────────────────────────────────────────────

    @Test
    void webhooks_register_returnsWebhook() throws Exception {
        UUID agentId = UUID.fromString("00000000-0000-0000-0000-000000000002");
        server.enqueue(new MockResponse().setResponseCode(201)
                .setBody(WEBHOOK_JSON)
                .addHeader("Content-Type", "application/json"));

        Webhook wh = client.webhooks().register(agentId, "https://example.com/hook");

        assertNotNull(wh.getId());
        assertEquals("https://example.com/hook", wh.getUrl());
        assertTrue(wh.isActive());

        RecordedRequest req = server.takeRequest();
        assertEquals("/agents/" + agentId + "/webhooks", req.getPath());
        assertEquals("POST", req.getMethod());
    }

    @Test
    void webhooks_register_withEventsAndSecret_sendsThemInBody() throws Exception {
        UUID agentId = UUID.fromString("00000000-0000-0000-0000-000000000002");
        server.enqueue(new MockResponse().setResponseCode(201)
                .setBody(WEBHOOK_JSON)
                .addHeader("Content-Type", "application/json"));

        client.webhooks().register(
                agentId,
                "https://example.com/hook",
                List.of("ALLOW", "DENY", "ESCALATE"),
                "my-secret"
        );

        RecordedRequest req = server.takeRequest();
        String body = req.getBody().readUtf8();
        assertTrue(body.contains("ALLOW"));
        assertTrue(body.contains("my-secret"));
    }

    @Test
    void webhooks_list_returnsListOfWebhooks() throws Exception {
        UUID agentId = UUID.fromString("00000000-0000-0000-0000-000000000002");
        server.enqueue(new MockResponse()
                .setBody("[" + WEBHOOK_JSON + "]")
                .addHeader("Content-Type", "application/json"));

        List<Webhook> webhooks = client.webhooks().list(agentId);
        assertEquals(1, webhooks.size());
        assertEquals("https://example.com/hook", webhooks.get(0).getUrl());
    }

    @Test
    void webhooks_delete_sends204Delete() throws Exception {
        UUID webhookId = UUID.fromString("00000000-0000-0000-0000-000000000005");
        server.enqueue(new MockResponse().setResponseCode(204));

        assertDoesNotThrow(() -> client.webhooks().delete(webhookId));

        RecordedRequest req = server.takeRequest();
        assertEquals("/webhooks/" + webhookId, req.getPath());
        assertEquals("DELETE", req.getMethod());
    }

    // ── Templates ────────────────────────────────────────────────────────────

    @Test
    void templates_list_returnsTemplates() throws Exception {
        server.enqueue(new MockResponse()
                .setBody("[" + TEMPLATE_JSON + "]")
                .addHeader("Content-Type", "application/json"));

        List<TemplateInfo> templates = client.templates().list();
        assertEquals(1, templates.size());
        assertEquals("nbe_payment_agent", templates.get(0).getName());
        assertEquals("Ethiopia", templates.get(0).getJurisdiction());

        RecordedRequest req = server.takeRequest();
        assertEquals("/templates", req.getPath());
        assertEquals("GET", req.getMethod());
        // Templates endpoint requires no X-API-Key but client can send it
    }

    @Test
    void templates_get_returnsTemplate() throws Exception {
        server.enqueue(new MockResponse()
                .setBody(TEMPLATE_JSON)
                .addHeader("Content-Type", "application/json"));

        TemplateInfo t = client.templates().get("nbe_payment_agent");
        assertEquals("NBE Payment Agent", t.getDisplayName());
        assertEquals("National Bank of Ethiopia (NBE)", t.getRegulator());
        assertEquals(1, t.getRuleCount());
        assertFalse(t.getReferences().isEmpty());

        RecordedRequest req = server.takeRequest();
        assertEquals("/templates/nbe_payment_agent", req.getPath());
    }

    @Test
    void templates_listByRegulator_sendsRegulatorParam() throws Exception {
        server.enqueue(new MockResponse()
                .setBody("[" + TEMPLATE_JSON + "]")
                .addHeader("Content-Type", "application/json"));

        client.templates().listByRegulator("National Bank of Ethiopia (NBE)");

        RecordedRequest req = server.takeRequest();
        assertTrue(req.getPath().contains("regulator="));
    }

    @Test
    void templates_listByTag_sendsTagParam() throws Exception {
        server.enqueue(new MockResponse()
                .setBody("[" + TEMPLATE_JSON + "]")
                .addHeader("Content-Type", "application/json"));

        client.templates().listByTag("payment");

        RecordedRequest req = server.takeRequest();
        assertTrue(req.getPath().contains("tag=payment"));
    }

    // ── Error handling ────────────────────────────────────────────────────────

    @Test
    void http_error_throwsIOException() {
        server.enqueue(new MockResponse()
                .setResponseCode(401)
                .setBody("{\"detail\": \"X-API-Key header is required.\"}"));

        assertThrows(IOException.class, () -> client.policies().list());
    }

    @Test
    void http_404_throwsIOException() {
        UUID nonExistent = UUID.randomUUID();
        server.enqueue(new MockResponse()
                .setResponseCode(404)
                .setBody("{\"detail\": \"Agent not found\"}"));

        assertThrows(IOException.class, () -> client.agents().get(nonExistent));
    }

    // ── Model helper methods ──────────────────────────────────────────────────

    @Test
    void permissionDecision_enumHelpers_workCorrectly() {
        // Test enum helpers without HTTP
        assertEquals(DecisionResult.ALLOW, DecisionResult.fromValue("ALLOW"));
        assertEquals(DecisionResult.DENY, DecisionResult.fromValue("deny"));
        assertEquals(DecisionResult.ESCALATE, DecisionResult.fromValue("ESCALATE"));
        assertThrows(IllegalArgumentException.class, () -> DecisionResult.fromValue("UNKNOWN"));

        assertEquals(ConfidenceLevel.HIGH, ConfidenceLevel.fromValue("HIGH"));
        assertEquals(ConfidenceLevel.MEDIUM, ConfidenceLevel.fromValue("medium"));
        assertThrows(IllegalArgumentException.class, () -> ConfidenceLevel.fromValue("BAD"));

        assertEquals(AgentScope.READ, AgentScope.fromValue("read"));
        assertEquals(AgentScope.EXECUTE, AgentScope.fromValue("EXECUTE"));
    }

    @Test
    void agentAuthClient_apiKeyHeader_isSentOnEveryRequest() throws Exception {
        // Three different requests — all should carry the X-API-Key header
        server.enqueue(new MockResponse().setBody("[" + POLICY_JSON + "]").addHeader("Content-Type", "application/json"));
        server.enqueue(new MockResponse().setBody("[" + AGENT_JSON + "]").addHeader("Content-Type", "application/json"));
        server.enqueue(new MockResponse().setBody("{\"status\":\"healthy\"}").addHeader("Content-Type", "application/json"));

        client.policies().list();
        client.agents().list("user_1");
        client.health();

        for (int i = 0; i < 3; i++) {
            RecordedRequest req = server.takeRequest();
            assertEquals(API_KEY, req.getHeader("X-API-Key"),
                    "Request " + i + " (" + req.getPath() + ") missing X-API-Key");
        }
    }
}
