package com.alibaba.cloud.ai.dataagentbackend.llm.anthropic;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Objects;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;

/**
 * Anthropic 协议兼容的 Messages API 最小客户端。
 */
public class AnthropicClient {

	private final WebClient webClient;

	private final AnthropicProperties props;

	private final ObjectMapper objectMapper;

	private static final ParameterizedTypeReference<ServerSentEvent<String>> SSE_STRING_TYPE = new ParameterizedTypeReference<>() {
	};

	public AnthropicClient(WebClient.Builder builder, AnthropicProperties props, ObjectMapper objectMapper) {
		this.props = props;
		this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
		WebClient.Builder b = builder.baseUrl(props.baseUrl());

		// Anthropic 标准认证头是 x-api-key；部分网关也兼容 Authorization: Bearer
		if (StringUtils.hasText(props.apiKey())) {
			b.defaultHeader("x-api-key", props.apiKey());
			b.defaultHeader("Authorization", "Bearer " + props.apiKey());
		}
		if (StringUtils.hasText(props.anthropicVersion())) {
			b.defaultHeader("anthropic-version", props.anthropicVersion());
		}

		this.webClient = b.build();
	}

	public Mono<String> createMessage(String systemPrompt, String userPrompt) {
		MessageRequest req = new MessageRequest(props.model(), props.maxTokens(), props.temperature(), systemPrompt,
				List.of(new Message("user", List.of(new ContentBlock("text", userPrompt)))));

		return webClient.post()
			.uri("/v1/messages")
			.contentType(MediaType.APPLICATION_JSON)
			.bodyValue(req)
			.retrieve()
			.bodyToMono(MessageResponse.class)
			.map(MessageResponse::firstText);
	}

	/**
	 * 以 SSE 方式流式返回模型输出增量（仅提取文本 delta）。
	 * <p>
	 * 说明：该实现假设 SSE 的 {@code data} 是 JSON，且包含字段 {@code delta.type=text_delta} 与 {@code delta.text}。
	 * 如果 minimax 的实际返回结构不同，只需要调整 {@link #extractTextDelta(String)} 的解析即可。
	 */
	public Flux<String> streamMessage(String systemPrompt, String userPrompt) {
		StreamMessageRequest req = new StreamMessageRequest(props.model(), props.maxTokens(), props.temperature(),
				systemPrompt, List.of(new Message("user", List.of(new ContentBlock("text", userPrompt)))), true);

		return webClient.post()
			.uri("/v1/messages")
			.accept(MediaType.TEXT_EVENT_STREAM)
			.contentType(MediaType.APPLICATION_JSON)
			.bodyValue(req)
			.retrieve()
			.bodyToFlux(SSE_STRING_TYPE)
			.mapNotNull(sse -> {
				if (sse == null) {
					return null;
				}
				String data = sse.data();
				if (!StringUtils.hasText(data)) {
					return null;
				}
				return extractTextDelta(data);
			})
			.filter(StringUtils::hasText)
			.onErrorMap(WebClientResponseException.class,
					ex -> new RuntimeException("LLM request failed: " + ex.getStatusCode() + " " + ex.getResponseBodyAsString(), ex));
	}

	public record MessageRequest(String model, int max_tokens, double temperature, String system, List<Message> messages) {
	}

	public record StreamMessageRequest(String model, int max_tokens, double temperature, String system,
			List<Message> messages, boolean stream) {
	}

	public record Message(String role, List<ContentBlock> content) {
	}

	public record ContentBlock(String type, String text) {
	}

	public record MessageResponse(List<ContentBlock> content) {
		public String firstText() {
			if (content == null || content.isEmpty()) {
				return "";
			}
			for (ContentBlock block : content) {
				if (block != null && "text".equals(block.type())) {
					return block.text() == null ? "" : block.text();
				}
			}
			return "";
		}
	}

	private String extractTextDelta(String json) {
		try {
			DeltaEnvelope env = objectMapper.readValue(json, DeltaEnvelope.class);
			if (env == null || env.delta == null) {
				return null;
			}
			if ("text_delta".equals(env.delta.type) && StringUtils.hasText(env.delta.text)) {
				return env.delta.text;
			}
			return null;
		}
		catch (JsonProcessingException ignored) {
			// 忽略未知/非文本 delta 的事件体
			return null;
		}
	}

	/**
	 * 用于匹配 Anthropic SSE 中常见的 "content_block_delta" 事件体结构（只关心 delta）。
	 */
	private static class DeltaEnvelope {
		public Delta delta;
	}

	private static class Delta {
		public String type;
		public String text;
	}

}
