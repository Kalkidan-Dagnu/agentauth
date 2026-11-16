package io.agentauth.sdk.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;

/**
 * A permission request made by an agent.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class Permission {
    @JsonProperty("action")
    private String action;

    @JsonProperty("resource")
    private String resource;

    @JsonProperty("context")
    private Map<String, Object> context;

    public Permission() {}

    public Permission(String action, String resource, Map<String, Object> context) {
        this.action = action;
        this.resource = resource;
        this.context = context;
    }

    public String getAction() { return action; }
    public String getResource() { return resource; }
    public Map<String, Object> getContext() { return context; }

    public void setAction(String action) { this.action = action; }
    public void setResource(String resource) { this.resource = resource; }
    public void setContext(Map<String, Object> context) { this.context = context; }

    @Override
    public String toString() {
        return "Permission{action='" + action + "', resource='" + resource + "'}";
    }
}
