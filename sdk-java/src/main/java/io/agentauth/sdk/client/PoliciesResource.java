package io.agentauth.sdk.client;

import io.agentauth.sdk.model.Policy;
import com.fasterxml.jackson.core.type.TypeReference;

import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * SDK resource for managing policies and templates.
 */
public class PoliciesResource {
    private final HttpHelper http;

    PoliciesResource(HttpHelper http) {
        this.http = http;
    }

    public Policy create(
            String name,
            List<String> rules,
            String description,
            Map<String, Object> metadata
    ) throws IOException {
        Map<String, Object> body = new HashMap<>();
        body.put("name", name);
        body.put("rules", rules);
        body.put("description", description != null ? description : "");
        body.put("metadata", metadata != null ? metadata : Map.of());

        String json = http.post("/policies", body);
        return http.getMapper().readValue(json, Policy.class);
    }

    public Policy create(String name, List<String> rules) throws IOException {
        return create(name, rules, null, null);
    }

    public Policy get(String policyId) throws IOException {
        String json = http.get("/policies/" + policyId);
        return http.getMapper().readValue(json, Policy.class);
    }

    public List<Policy> list() throws IOException {
        String json = http.get("/policies");
        return http.getMapper().readValue(json, new TypeReference<List<Policy>>() {});
    }

    // ── Template methods ──────────────────────────────────────────────────────

    public Policy createFromTemplate(
            String templateName,
            String policyName,
            String description,
            List<String> overrides
    ) throws IOException {
        Map<String, Object> body = new HashMap<>();
        body.put("template_name", templateName);
        body.put("policy_name", policyName);
        body.put("description", description != null ? description : "");
        body.put("overrides", overrides != null ? overrides : List.of());

        String json = http.post("/policies/from-template", body);
        return http.getMapper().readValue(json, Policy.class);
    }

    public Policy createFromTemplate(String templateName, String policyName) throws IOException {
        return createFromTemplate(templateName, policyName, null, null);
    }
}
