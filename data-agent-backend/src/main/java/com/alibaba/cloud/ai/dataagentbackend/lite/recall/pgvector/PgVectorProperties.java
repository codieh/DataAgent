package com.alibaba.cloud.ai.dataagentbackend.lite.recall.pgvector;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "search.lite.recall.pgvector")
public record PgVectorProperties(boolean enabled, String url, String username, String password, String tableName,
		int dimensions, boolean syncOnSearch) {

	public PgVectorProperties {
		url = normalize(url, "jdbc:postgresql://localhost:5432/data_agent_recall");
		username = normalize(username, "postgres");
		password = password == null ? "" : password;
		tableName = normalize(tableName, "recall_vectors");
		dimensions = dimensions <= 0 ? 1024 : dimensions;
	}

	private static String normalize(String value, String fallback) {
		if (value == null || value.isBlank()) {
			return fallback;
		}
		return value.trim();
	}

}
