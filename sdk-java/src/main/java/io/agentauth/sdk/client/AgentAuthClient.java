package io.agentauth.sdk.client;

import java.time.Duration;
import java.io.IOException;

/**
 * The AgentAuth Java SDK client.
 *
 * Provides a clean, resource-based interface to the AgentAuth server.
 * Handles HTTP connections, API key authentication (X-API-Key header),
 * and JSON serialisation.
 *
 * <p>Usage:
 * <pre>{@code
 * AgentAuthClient client = new AgentAuthClient("http://localhost:8000", "aak_your_key");
 *
 * // Create a policy from an NBE template
 * Policy policy = client.policies().createFromTemplate(
 *     "nbe_payment_agent", "my-payment-policy"
 * );
 *
 * // Register an agent
 * Agent agent = client.agents().register("trading-bot", "user_123");
 *
 * // Check permission before acting
 * if (client.permissions().isAllowed(agent.getId(), "buy", "BTCUSDT")) {
 *     executeTrade();
 * }
 * }</pre>
 */
public class AgentAuthClient implements AutoCloseable {
    private final HttpHelper http;

    private final AgentsResource agents;
    private final PoliciesResource policies;
    private final PermissionsResource permissions;
    private final WebhookResource webhooks;
    private final TemplateResource templates;

    /**
     * Create a new AgentAuth client.
     *
     * @param baseUrl The AgentAuth server URL (e.g. "http://localhost:8000").
     * @param apiKey The organisation API key (starts with "aak_"). Required for all
     *               org-scoped endpoints. Pass null for public endpoints (templates listing).
     * @param timeout Request timeout. Default is 30 seconds.
     */
    public AgentAuthClient(String baseUrl, String apiKey, Duration timeout) {
        Duration t = timeout != null ? timeout : Duration.ofSeconds(30);
        this.http = new HttpHelper(baseUrl, apiKey, t);
        this.agents = new AgentsResource(http);
        this.policies = new PoliciesResource(http);
        this.permissions = new PermissionsResource(http);
        this.webhooks = new WebhookResource(http);
        this.templates = new TemplateResource(http);
    }

    public AgentAuthClient(String baseUrl, String apiKey) {
        this(baseUrl, apiKey, Duration.ofSeconds(30));
    }

    public AgentsResource agents() { return agents; }
    public PoliciesResource policies() { return policies; }
    public PermissionsResource permissions() { return permissions; }
    public WebhookResource webhooks() { return webhooks; }
    public TemplateResource templates() { return templates; }

    public String health() throws IOException {
        return http.get("/health");
    }

    @Override
    public void close() {
        http.close();
    }
}
