package com.alibaba.cloud.ai.dataagentbackend.llm.anthropic;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "llm.anthropic")
public record AnthropicProperties(String baseUrl, String apiKey, String model, double temperature, int maxTokens,
		String anthropicVersion, int requestTimeoutSeconds, int streamTimeoutSeconds) {

	public AnthropicProperties {
		requestTimeoutSeconds = requestTimeoutSeconds <= 0 ? 30 : requestTimeoutSeconds;
		streamTimeoutSeconds = streamTimeoutSeconds <= 0 ? 60 : streamTimeoutSeconds;
	}
}
