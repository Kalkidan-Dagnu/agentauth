package io.agentauth.sdk.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.Map;
import java.util.UUID;

/**
 * A tenant organisation in AgentAuth.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class Organization {
    @JsonProperty("id")
    private UUID id;

    @JsonProperty("name")
    private String name;

    @JsonProperty("slug")
    private String slug;

    @JsonProperty("description")
    private String description = "";

    @JsonProperty("owner_id")
    private String ownerId;

    @JsonProperty("is_active")
    private boolean active = true;

    @JsonProperty("created_at")
    private String createdAt;

    @JsonProperty("metadata")
    private Map<String, Object> metadata;

    public Organization() {}

    public UUID getId() { return id; }
    public String getName() { return name; }
    public String getSlug() { return slug; }
    public String getDescription() { return description; }
    public String getOwnerId() { return ownerId; }
    public boolean isActive() { return active; }
    public String getCreatedAt() { return createdAt; }
    public Map<String, Object> getMetadata() { return metadata; }

    public void setId(UUID id) { this.id = id; }
    public void setName(String name) { this.name = name; }
    public void setSlug(String slug) { this.slug = slug; }
    public void setDescription(String description) { this.description = description; }
    public void setOwnerId(String ownerId) { this.ownerId = ownerId; }
    public void setActive(boolean active) { this.active = active; }
    public void setCreatedAt(String createdAt) { this.createdAt = createdAt; }
    public void setMetadata(Map<String, Object> metadata) { this.metadata = metadata; }

    @Override
    public String toString() {
        return "Organization{id=" + id + ", name='" + name + "', slug='" + slug + "'}";
    }
}
