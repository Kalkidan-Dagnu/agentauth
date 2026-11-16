package io.agentauth.sdk.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.UUID;

/**
 * The result of evaluating a permission request against policies using Gemini.
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class PermissionDecision {
    @JsonProperty("request_id")
    private UUID requestId;

    @JsonProperty("agent_id")
    private UUID agentId;

    @JsonProperty("permission")
    private Permission permission;

    @JsonProperty("result")
    private String result;

    @JsonProperty("reason")
    private String reason;

    @JsonProperty("confidence")
    private String confidence;

    @JsonProperty("matched_rules")
    private List<String> matchedRules;

    @JsonProperty("evaluated_at")
    private String evaluatedAt;

    @JsonProperty("latency_ms")
    private double latencyMs;

    public PermissionDecision() {}

    // Convenience getters for enums
    public DecisionResult getDecisionResult() {
        return result != null ? DecisionResult.fromValue(result) : null;
    }

    public ConfidenceLevel getConfidenceLevel() {
        return confidence != null ? ConfidenceLevel.fromValue(confidence) : null;
    }

    public boolean isAllowed() {
        return "ALLOW".equalsIgnoreCase(result);
    }

    public boolean isDenied() {
        return "DENY".equalsIgnoreCase(result);
    }

    public boolean isEscalate() {
        return "ESCALATE".equalsIgnoreCase(result);
    }

    // Standard getters
    public UUID getRequestId() { return requestId; }
    public UUID getAgentId() { return agentId; }
    public Permission getPermission() { return permission; }
    public String getResult() { return result; }
    public String getReason() { return reason; }
    public String getConfidence() { return confidence; }
    public List<String> getMatchedRules() { return matchedRules; }
    public String getEvaluatedAt() { return evaluatedAt; }
    public double getLatencyMs() { return latencyMs; }

    // Setters
    public void setRequestId(UUID requestId) { this.requestId = requestId; }
    public void setAgentId(UUID agentId) { this.agentId = agentId; }
    public void setPermission(Permission permission) { this.permission = permission; }
    public void setResult(String result) { this.result = result; }
    public void setReason(String reason) { this.reason = reason; }
    public void setConfidence(String confidence) { this.confidence = confidence; }
    public void setMatchedRules(List<String> matchedRules) { this.matchedRules = matchedRules; }
    public void setEvaluatedAt(String evaluatedAt) { this.evaluatedAt = evaluatedAt; }
    public void setLatencyMs(double latencyMs) { this.latencyMs = latencyMs; }

    @Override
    public String toString() {
        return "PermissionDecision{result=" + result + ", reason='" + reason + "', confidence=" + confidence + "}";
    }
}
