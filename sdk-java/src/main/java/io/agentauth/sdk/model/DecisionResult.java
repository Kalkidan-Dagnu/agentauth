package io.agentauth.sdk.model;

/**
 * The outcome of a permission evaluation.
 */
public enum DecisionResult {
    ALLOW("ALLOW"),
    DENY("DENY"),
    ESCALATE("ESCALATE");

    private final String value;

    DecisionResult(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public static DecisionResult fromValue(String value) {
        for (DecisionResult r : values()) {
            if (r.value.equalsIgnoreCase(value)) {
                return r;
            }
        }
        throw new IllegalArgumentException("Unknown decision result: " + value);
    }
}
