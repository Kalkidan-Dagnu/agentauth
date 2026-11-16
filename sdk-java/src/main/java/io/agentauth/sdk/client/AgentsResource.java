package io.agentauth.sdk.client;

import io.agentauth.sdk.model.Agent;
import com.fasterxml.jackson.core.type.TypeReference;

import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * SDK resource for managing agents.
 */
public class AgentsResource {
    private final HttpHelper http;

    AgentsResource(HttpHelper http) {
        this.http = http;
    }

    public Agent register(
            String name,
            String ownerId,
            List<String> scopes,
            List<UUID> policyIds,
            String description
    ) throws IOException {
        Map<String, Object> body = new HashMap<>();
        body.put("name", name);
        body.put("owner_id", ownerId);
        body.put("scopes", scopes != null ? scopes : List.of());
        body.put("policy_ids", policyIds != null ? policyIds : List.of());
        body.put("description", description != null ? description : "");

        String json = http.post("/agents", body);
        return http.getMapper().readValue(json, Agent.class);
    }

    public Agent register(String name, String ownerId) throws IOException {
        return register(name, ownerId, null, null, null);
    }

    public Agent get(UUID agentId) throws IOException {
        String json = http.get("/agents/" + agentId);
        return http.getMapper().readValue(json, Agent.class);
    }

    public List<Agent> list(String ownerId) throws IOException {
        Map<String, String> params = new HashMap<>();
        params.put("owner_id", ownerId);
        String json = http.get("/agents", params);
        return http.getMapper().readValue(json, new TypeReference<List<Agent>>() {});
    }

    public boolean deactivate(UUID agentId) throws IOException {
        String json = http.post("/agents/" + agentId + "/deactivate", Map.of());
        Map<?, ?> result = http.getMapper().readValue(json, Map.class);
        return Boolean.TRUE.equals(result.get("success"));
    }
}
