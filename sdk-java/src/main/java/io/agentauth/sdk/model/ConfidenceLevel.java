package io.agentauth.sdk.model;

/**
 * Gemini's confidence in its decision.
 */
public enum ConfidenceLevel {
    HIGH("HIGH"),
    MEDIUM("MEDIUM"),
    LOW("LOW");

    private final String value;

    ConfidenceLevel(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public static ConfidenceLevel fromValue(String value) {
        for (ConfidenceLevel c : values()) {
            if (c.value.equalsIgnoreCase(value)) {
                return c;
            }
        }
        throw new IllegalArgumentException("Unknown confidence level: " + value);
    }
}
