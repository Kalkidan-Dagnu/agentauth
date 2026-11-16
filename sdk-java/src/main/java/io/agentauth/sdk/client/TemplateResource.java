package io.agentauth.sdk.client;

import io.agentauth.sdk.model.TemplateInfo;
import com.fasterxml.jackson.core.type.TypeReference;

import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * SDK resource for browsing policy templates.
 */
public class TemplateResource {
    private final HttpHelper http;

    public TemplateResource(HttpHelper http) {
        this.http = http;
    }

    public List<TemplateInfo> list() throws IOException {
        String json = http.get("/templates");
        return http.getMapper().readValue(json, new TypeReference<List<TemplateInfo>>() {});
    }

    public List<TemplateInfo> listByRegulator(String regulator) throws IOException {
        Map<String, String> params = new HashMap<>();
        params.put("regulator", regulator);
        String json = http.get("/templates", params);
        return http.getMapper().readValue(json, new TypeReference<List<TemplateInfo>>() {});
    }

    public List<TemplateInfo> listByTag(String tag) throws IOException {
        Map<String, String> params = new HashMap<>();
        params.put("tag", tag);
        String json = http.get("/templates", params);
        return http.getMapper().readValue(json, new TypeReference<List<TemplateInfo>>() {});
    }

    public TemplateInfo get(String templateName) throws IOException {
        String json = http.get("/templates/" + templateName);
        return http.getMapper().readValue(json, TemplateInfo.class);
    }
}
