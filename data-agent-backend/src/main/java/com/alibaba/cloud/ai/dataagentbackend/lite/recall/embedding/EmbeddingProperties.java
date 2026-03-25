package com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 本地 embedding 配置。
 */
@ConfigurationProperties(prefix = "search.lite.recall.vector.embedding")
public record EmbeddingProperties(String baseUrl, String apiKey, String model, String path) {
}
