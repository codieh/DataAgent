package com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.List;
import java.util.Objects;

/**
 * 兼容 OpenAI embeddings 协议的本地 embedding client。
 */
@Component
@EnableConfigurationProperties(EmbeddingProperties.class)
public class LocalEmbeddingClient implements EmbeddingClient {

	private static final Logger log = LoggerFactory.getLogger(LocalEmbeddingClient.class);

	private final EmbeddingProperties properties;

	private final ObjectMapper objectMapper;

	private final HttpClient httpClient;

	public LocalEmbeddingClient(EmbeddingProperties properties, ObjectMapper objectMapper) {
		this.properties = Objects.requireNonNull(properties, "properties");
		this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
		this.httpClient = HttpClient.newBuilder()
			.connectTimeout(Duration.ofSeconds(resolveConnectTimeoutSeconds()))
			.version(HttpClient.Version.HTTP_1_1)
			.build();
	}

	@Override
	public List<Double> embed(String text) {
		String content = text == null ? "" : text.trim();
		if (content.isBlank()) {
			return List.of();
		}

		EmbeddingRequest request = new EmbeddingRequest(
				StringUtils.hasText(properties.model()) ? properties.model().trim() : "bge-m3", content);
		String url = resolveUrl();
		long startedAt = System.nanoTime();
		try {
			log.info("embedding 请求开始：url={}, model={}, textLen={}, connectTimeoutSec={}, requestTimeoutSec={}", url,
					request.model(), content.length(), resolveConnectTimeoutSeconds(), resolveRequestTimeoutSeconds());
			HttpRequest.Builder builder = HttpRequest.newBuilder()
				.uri(URI.create(url))
				.timeout(Duration.ofSeconds(resolveRequestTimeoutSeconds()))
				.header("Content-Type", "application/json");
			if (StringUtils.hasText(properties.apiKey())) {
				builder.header("Authorization", "Bearer " + properties.apiKey().trim());
			}

			HttpResponse<String> response = httpClient.send(
					builder.POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(request))).build(),
					HttpResponse.BodyHandlers.ofString());
			long tookMs = (System.nanoTime() - startedAt) / 1_000_000;
			log.info("embedding 请求结束：url={}, model={}, status={}, textLen={}, tookMs={}", url, request.model(),
					response.statusCode(), content.length(), tookMs);

			if (response.statusCode() >= 400) {
				log.warn("embedding 调用失败：url={}, model={}, status={}, textLen={}, tookMs={}", url, request.model(),
						response.statusCode(), content.length(), tookMs);
				return List.of();
			}

			EmbeddingResponse body = objectMapper.readValue(response.body(), EmbeddingResponse.class);
			if (body == null || body.data() == null || body.data().isEmpty() || body.data().get(0).embedding() == null) {
				log.warn("embedding 响应为空：url={}, model={}, textLen={}, tookMs={}", url, request.model(),
						content.length(), tookMs);
				return List.of();
			}
			return body.data().get(0).embedding();
		}
		catch (HttpTimeoutException e) {
			log.warn("embedding 调用超时：url={}, model={}, textLen={}, requestTimeoutSec={}, error={}", url,
					request.model(), content.length(), resolveRequestTimeoutSeconds(), e.getMessage());
			return List.of();
		}
		catch (Exception e) {
			log.warn("embedding 调用失败：url={}, model={}, textLen={}, error={}", url, request.model(),
					content.length(), e.getMessage());
			return List.of();
		}
	}

	private String resolveUrl() {
		String baseUrl = StringUtils.hasText(properties.baseUrl()) ? properties.baseUrl().trim() : "http://127.0.0.1:1234";
		String path = StringUtils.hasText(properties.path()) ? properties.path().trim() : "/v1/embeddings";
		if (!path.startsWith("/")) {
			path = "/" + path;
		}
		if (baseUrl.endsWith("/")) {
			baseUrl = baseUrl.substring(0, baseUrl.length() - 1);
		}
		return baseUrl + path;
	}

	private int resolveConnectTimeoutSeconds() {
		return properties.connectTimeoutSeconds() == null ? 10 : Math.max(1, properties.connectTimeoutSeconds());
	}

	private int resolveRequestTimeoutSeconds() {
		return properties.requestTimeoutSeconds() == null ? 30 : Math.max(1, properties.requestTimeoutSeconds());
	}

	private record EmbeddingRequest(String model, String input) {
	}

	private record EmbeddingResponse(List<EmbeddingData> data) {
	}

	private record EmbeddingData(List<Double> embedding) {
	}

}
