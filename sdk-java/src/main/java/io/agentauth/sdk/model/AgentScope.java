package io.agentauth.sdk.model;

/**
 * Predefined scopes an agent can be granted.
 */
public enum AgentScope {
    READ("read"),
    WRITE("write"),
    EXECUTE("execute"),
    ADMIN("admin"),
    CUSTOM("custom");

    private final String value;

    AgentScope(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public static AgentScope fromValue(String value) {
        for (AgentScope scope : values()) {
            if (scope.value.equalsIgnoreCase(value)) {
                return scope;
            }
        }
        throw new IllegalArgumentException("Unknown scope: " + value);
    }
}
