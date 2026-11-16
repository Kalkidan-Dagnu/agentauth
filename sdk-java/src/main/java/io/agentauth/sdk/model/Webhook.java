package io.agentauth.sdk.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * A webhook endpoint registered to receive PermissionDecision notifications.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class Webhook {
    @JsonProperty("id")
    private UUID id;

    @JsonProperty("agent_id")
    private UUID agentId;

    @JsonProperty("url")
    private String url;

    @JsonProperty("events")
    private List<String> events;

    @JsonProperty("secret")
    private String secret;

    @JsonProperty("is_active")
    private boolean active = true;

    @JsonProperty("created_at")
    private String createdAt;

    public Webhook() {}

    public UUID getId() { return id; }
    public UUID getAgentId() { return agentId; }
    public String getUrl() { return url; }
    public List<String> getEvents() { return events; }
    public String getSecret() { return secret; }
    public boolean isActive() { return active; }
    public String getCreatedAt() { return createdAt; }

    public void setId(UUID id) { this.id = id; }
    public void setAgentId(UUID agentId) { this.agentId = agentId; }
    public void setUrl(String url) { this.url = url; }
    public void setEvents(List<String> events) { this.events = events; }
    public void setSecret(String secret) { this.secret = secret; }
    public void setActive(boolean active) { this.active = active; }
    public void setCreatedAt(String createdAt) { this.createdAt = createdAt; }

    @Override
    public String toString() {
        return "Webhook{id=" + id + ", url='" + url + "', events=" + events + "}";
    }
}
