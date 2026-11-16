package io.agentauth.sdk.client;

import okhttp3.OkHttpClient;
import okhttp3.MediaType;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

import java.io.IOException;
import java.time.Duration;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

/**
 * Internal HTTP helper shared by all resources.
 * Handles base URL, API key header, JSON serialisation, and error handling.
 */
class HttpHelper {
    private final OkHttpClient client;
    private final String baseUrl;
    private final String apiKey;
    private final ObjectMapper mapper;

    static final MediaType JSON_TYPE = MediaType.get("application/json; charset=utf-8");

    HttpHelper(String baseUrl, String apiKey, Duration timeout) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.apiKey = apiKey;
        this.client = new OkHttpClient.Builder()
                .connectTimeout(timeout)
                .readTimeout(timeout)
                .writeTimeout(timeout)
                .build();
        this.mapper = new ObjectMapper();
        this.mapper.registerModule(new JavaTimeModule());
        this.mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }

    ObjectMapper getMapper() {
        return mapper;
    }

    String getBaseUrl() {
        return baseUrl;
    }

    OkHttpClient getClient() {
        return client;
    }

    private Request.Builder requestBuilder(String path) {
        Request.Builder builder = new Request.Builder()
                .url(baseUrl + path)
                .header("Content-Type", "application/json");
        if (apiKey != null) {
            builder.header("X-API-Key", apiKey);
        }
        return builder;
    }

    String get(String path) throws IOException {
        Request request = requestBuilder(path).get().build();
        try (Response response = client.newCall(request).execute()) {
            return handleResponse(response);
        }
    }

    String get(String path, Map<String, String> params) throws IOException {
        if (params != null && !params.isEmpty()) {
            StringBuilder sb = new StringBuilder(path);
            sb.append("?");
            boolean first = true;
            for (Map.Entry<String, String> entry : params.entrySet()) {
                if (!first) sb.append("&");
                sb.append(entry.getKey()).append("=").append(entry.getValue());
                first = false;
            }
            path = sb.toString();
        }
        return get(path);
    }

    String post(String path, Object body) throws IOException {
        String json = mapper.writeValueAsString(body);
        RequestBody requestBody = RequestBody.create(json, JSON_TYPE);
        Request request = requestBuilder(path).post(requestBody).build();
        try (Response response = client.newCall(request).execute()) {
            return handleResponse(response);
        }
    }

    void delete(String path) throws IOException {
        Request request = requestBuilder(path).delete().build();
        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful() && response.code() != 204) {
                throw new IOException("HTTP " + response.code() + ": " + response.body().string());
            }
        }
    }

    private String handleResponse(Response response) throws IOException {
        String body = response.body() != null ? response.body().string() : "";
        if (!response.isSuccessful()) {
            throw new IOException("HTTP " + response.code() + ": " + body);
        }
        return body;
    }

    void close() {
        client.dispatcher().executorService().shutdown();
        client.connectionPool().evictAll();
    }
}
