package io.agentauth.sdk.client;

import io.agentauth.sdk.model.Webhook;
import com.fasterxml.jackson.core.type.TypeReference;

import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * SDK resource for managing webhooks.
 */
public class WebhookResource {
    private final HttpHelper http;

    WebhookResource(HttpHelper http) {
        this.http = http;
    }

    public Webhook register(
            UUID agentId,
            String url,
            List<String> events,
            String secret
    ) throws IOException {
        Map<String, Object> body = new HashMap<>();
        body.put("url", url);
        body.put("events", events != null ? events : List.of("ESCALATE"));
        if (secret != null) {
            body.put("secret", secret);
        }

        String json = http.post("/agents/" + agentId + "/webhooks", body);
        return http.getMapper().readValue(json, Webhook.class);
    }

    public Webhook register(UUID agentId, String url) throws IOException {
        return register(agentId, url, null, null);
    }

    public List<Webhook> list(UUID agentId) throws IOException {
        String json = http.get("/agents/" + agentId + "/webhooks");
        return http.getMapper().readValue(json, new TypeReference<List<Webhook>>() {});
    }

    public void delete(UUID webhookId) throws IOException {
        http.delete("/webhooks/" + webhookId);
    }
}
