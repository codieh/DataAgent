package com.alibaba.cloud.ai.dataagentbackend.lite.recall.chroma;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "search.lite.recall.chroma")
public record ChromaProperties(boolean enabled, String baseUrl, String collectionName, String tenant, String database,
		String token, boolean syncOnSearch) {

	public ChromaProperties {
		baseUrl = normalize(baseUrl, "http://localhost:8000");
		collectionName = normalize(collectionName, "data-agent-backend-recall");
		tenant = normalize(tenant, "default_tenant");
		database = normalize(database, "default_database");
		token = token == null ? "" : token.trim();
	}

	private static String normalize(String value, String fallback) {
		if (value == null || value.isBlank()) {
			return fallback;
		}
		return value.trim();
	}

}
