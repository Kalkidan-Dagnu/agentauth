package io.agentauth.sdk.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Represents an AI agent registered in AgentAuth.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class Agent {
    @JsonProperty("id")
    private UUID id;

    @JsonProperty("name")
    private String name;

    @JsonProperty("description")
    private String description = "";

    @JsonProperty("owner_id")
    private String ownerId;

    @JsonProperty("scopes")
    private List<String> scopes;

    @JsonProperty("policy_ids")
    private List<UUID> policyIds;

    @JsonProperty("is_active")
    private boolean active = true;

    @JsonProperty("created_at")
    private String createdAt;

    @JsonProperty("metadata")
    private Map<String, Object> metadata;

    public Agent() {}

    public UUID getId() { return id; }
    public String getName() { return name; }
    public String getDescription() { return description; }
    public String getOwnerId() { return ownerId; }
    public List<String> getScopes() { return scopes; }
    public List<UUID> getPolicyIds() { return policyIds; }
    public boolean isActive() { return active; }
    public String getCreatedAt() { return createdAt; }
    public Map<String, Object> getMetadata() { return metadata; }

    public void setId(UUID id) { this.id = id; }
    public void setName(String name) { this.name = name; }
    public void setDescription(String description) { this.description = description; }
    public void setOwnerId(String ownerId) { this.ownerId = ownerId; }
    public void setScopes(List<String> scopes) { this.scopes = scopes; }
    public void setPolicyIds(List<UUID> policyIds) { this.policyIds = policyIds; }
    public void setActive(boolean active) { this.active = active; }
    public void setCreatedAt(String createdAt) { this.createdAt = createdAt; }
    public void setMetadata(Map<String, Object> metadata) { this.metadata = metadata; }

    @Override
    public String toString() {
        return "Agent{id=" + id + ", name='" + name + "', owner='" + ownerId + "', active=" + active + "}";
    }
}
