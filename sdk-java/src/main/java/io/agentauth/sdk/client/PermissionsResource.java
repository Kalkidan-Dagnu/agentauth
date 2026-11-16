package io.agentauth.sdk.client;

import io.agentauth.sdk.model.PermissionDecision;
import io.agentauth.sdk.model.Permission;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * SDK resource for evaluating permissions.
 */
public class PermissionsResource {
    private final HttpHelper http;

    PermissionsResource(HttpHelper http) {
        this.http = http;
    }

    public PermissionDecision evaluate(
            UUID agentId,
            String action,
            String resource,
            Map<String, Object> context
    ) throws IOException {
        Map<String, Object> body = new HashMap<>();
        body.put("action", action);
        body.put("resource", resource);
        body.put("context", context != null ? context : Map.of());

        String json = http.post("/agents/" + agentId + "/evaluate", body);
        return http.getMapper().readValue(json, PermissionDecision.class);
    }

    public PermissionDecision evaluate(
            UUID agentId,
            String action,
            String resource
    ) throws IOException {
        return evaluate(agentId, action, resource, null);
    }

    public boolean isAllowed(
            UUID agentId,
            String action,
            String resource,
            Map<String, Object> context
    ) throws IOException {
        return evaluate(agentId, action, resource, context).isAllowed();
    }

    public boolean isAllowed(UUID agentId, String action, String resource) throws IOException {
        return evaluate(agentId, action, resource).isAllowed();
    }
}
