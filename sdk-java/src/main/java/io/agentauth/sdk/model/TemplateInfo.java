package io.agentauth.sdk.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

/**
 * A template definition returned by GET /templates.
 * Stored as a generic map since templates are read-only metadata.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class TemplateInfo {
    @JsonProperty("name")
    private String name;

    @JsonProperty("display_name")
    private String displayName;

    @JsonProperty("description")
    private String description;

    @JsonProperty("regulator")
    private String regulator;

    @JsonProperty("jurisdiction")
    private String jurisdiction;

    @JsonProperty("version")
    private String version;

    @JsonProperty("rules")
    private List<String> rules;

    @JsonProperty("tags")
    private List<String> tags;

    @JsonProperty("references")
    private List<String> references;

    @JsonProperty("rule_count")
    private int ruleCount;

    public TemplateInfo() {}

    // Getters
    public String getName() { return name; }
    public String getDisplayName() { return displayName; }
    public String getDescription() { return description; }
    public String getRegulator() { return regulator; }
    public String getJurisdiction() { return jurisdiction; }
    public String getVersion() { return version; }
    public List<String> getRules() { return rules; }
    public List<String> getTags() { return tags; }
    public List<String> getReferences() { return references; }
    public int getRuleCount() { return ruleCount; }

    // Setters
    public void setName(String name) { this.name = name; }
    public void setDisplayName(String displayName) { this.displayName = displayName; }
    public void setDescription(String description) { this.description = description; }
    public void setRegulator(String regulator) { this.regulator = regulator; }
    public void setJurisdiction(String jurisdiction) { this.jurisdiction = jurisdiction; }
    public void setVersion(String version) { this.version = version; }
    public void setRules(List<String> rules) { this.rules = rules; }
    public void setTags(List<String> tags) { this.tags = tags; }
    public void setReferences(List<String> references) { this.references = references; }
    public void setRuleCount(int ruleCount) { this.ruleCount = ruleCount; }

    @Override
    public String toString() {
        return "TemplateInfo{name='" + name + "', displayName='" + displayName + "', rules=" + ruleCount + "}";
    }
}
