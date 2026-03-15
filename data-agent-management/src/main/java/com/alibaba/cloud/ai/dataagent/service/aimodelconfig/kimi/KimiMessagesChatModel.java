/*
 * Copyright 2024-2026 the original author or authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package com.alibaba.cloud.ai.dataagent.service.aimodelconfig.kimi;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.Generation;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.http.MediaType;
import org.springframework.util.StreamUtils;
import org.springframework.web.client.RestClient;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * Minimal ChatModel implementation for Kimi Coding (Anthropic Messages API-compatible).
 *
 * Note: Streaming is provided as a single-chunk Flux (non-token streaming).
 */
@Slf4j
public class KimiMessagesChatModel implements ChatModel {

	private final RestClient restClient;

	private final ObjectMapper objectMapper;

	private final String messagesPath;

	private final String modelName;

	private final Integer maxTokens;

	private final Double temperature;

	public KimiMessagesChatModel(RestClient restClient, ObjectMapper objectMapper, String messagesPath, String modelName,
			Integer maxTokens, Double temperature) {
		this.restClient = restClient;
		this.objectMapper = objectMapper;
		this.messagesPath = normalizePath(messagesPath);
		this.modelName = modelName;
		this.maxTokens = maxTokens;
		this.temperature = temperature;
	}

	/**
	 * Compatibility for code paths that call ChatModel#call(String) directly.
	 */
	public String call(String message) {
		ObjectNode root = objectMapper.createObjectNode();
		root.put("model", modelName);
		root.put("max_tokens", maxTokens != null ? maxTokens : 2000);
		root.put("stream", false);
		if (temperature != null) {
			root.put("temperature", temperature);
		}
		ArrayNode messages = root.putArray("messages");
		if (StringUtils.hasText(message)) {
			ObjectNode m = messages.addObject();
			m.put("role", "user");
			m.put("content", message);
		}

		String responseBody = postMessages(root);
		return StringUtils.trimWhitespace(extractAssistantText(responseBody == null ? "" : responseBody));
	}

	@Override
	public ChatResponse call(Prompt prompt) {
		ObjectNode request = buildRequest(prompt);
		return toChatResponse(postMessages(request));
	}

	@Override
	public Flux<ChatResponse> stream(Prompt prompt) {
		return Mono.fromCallable(() -> call(prompt))
				.subscribeOn(Schedulers.boundedElastic())
				.flatMapMany(response -> Flux.just(response));

	}

	private String postMessages(ObjectNode request) {
		try {
			String requestJson = objectMapper.writeValueAsString(request);
			if (log.isDebugEnabled()) {
				log.debug("Calling Kimi Messages API, uri: {}", messagesPath);
				log.debug("Kimi Messages API request size: {}", requestJson.length());
			}

			String responseBody = restClient.post()
				.uri(messagesPath)
				.accept(MediaType.APPLICATION_JSON)
				.header("Accept-Encoding", "identity")
				.header("Connection", "close")
				.contentType(MediaType.APPLICATION_JSON)
				.body(request)
				.exchange((req, res) -> {
					byte[] bytes = StreamUtils.copyToByteArray(res.getBody());
					String body = bytes == null ? null : new String(bytes, StandardCharsets.UTF_8);
					if (log.isDebugEnabled()) {
						String contentType = res.getHeaders().getContentType() != null ? res.getHeaders().getContentType().toString()
								: "null";
						long contentLength = res.getHeaders().getContentLength();
						int bodyLength = body == null ? -1 : body.length();
						int byteLength = bytes == null ? -1 : bytes.length;
						log.debug("Kimi Messages API status: {}, content-type: {}, content-length: {}, body-length: {}",
								res.getStatusCode().value(), contentType, contentLength, bodyLength);
						log.debug("Kimi Messages API byte-length: {}, first-bytes: {}", byteLength, toHexPreview(bytes, 32));
					}
					if (res.getStatusCode().isError()) {
						String preview = body == null ? "" : body.replaceAll("\\s+", " ");
						if (preview.length() > 400) {
							preview = preview.substring(0, 400) + "...";
						}
						throw new IllegalStateException(
								"Kimi Messages API returned HTTP " + res.getStatusCode().value() + ": " + preview);
					}
					return body;
				});

			if (log.isDebugEnabled() && responseBody != null) {
				String preview = responseBody.replaceAll("\\s+", " ");
				if (preview.length() > 400) {
					preview = preview.substring(0, 400) + "...";
				}
				log.debug("Kimi Messages API response preview: {}", preview);
			}

			return responseBody;
		}
		catch (Exception e) {
			throw new IllegalStateException("Failed to call Kimi Messages API: " + e.getMessage(), e);
		}
	}

	private ChatResponse toChatResponse(String responseBody) {
		if (!StringUtils.hasText(responseBody)) {
			return new ChatResponse(List.of(new Generation(new AssistantMessage(""))));
		}
		String text = extractAssistantText(responseBody);
		return new ChatResponse(List.of(new Generation(new AssistantMessage(text))));
	}

	private ObjectNode buildRequest(Prompt prompt) {
		ObjectNode root = objectMapper.createObjectNode();
		root.put("model", modelName);
		root.put("max_tokens", maxTokens != null ? maxTokens : 2000);
		root.put("stream", false);
		if (temperature != null) {
			root.put("temperature", temperature);
		}

		List<Message> instructions = prompt.getInstructions() == null ? List.of() : prompt.getInstructions();
		String systemText = buildSystemText(instructions);
		if (StringUtils.hasText(systemText)) {
			root.put("system", systemText);
		}

		ArrayNode messages = root.putArray("messages");
		for (Message message : instructions) {
			String role = resolveRole(message);
			if ("system".equals(role)) {
				continue;
			}
			String content = extractMessageText(message);
			if (!StringUtils.hasText(content)) {
				continue;
			}
			ObjectNode m = messages.addObject();
			m.put("role", role);
			m.put("content", content);
		}

		// If the Prompt didn't carry structured instructions, fall back to raw prompt text.
		if (messages.isEmpty()) {
			String content = extractPromptText(prompt);
			if (StringUtils.hasText(content)) {
				ObjectNode m = messages.addObject();
				m.put("role", "user");
				m.put("content", content);
			}
		}

		return root;
	}

	private String extractAssistantText(String responseBody) {
		try {
			JsonNode root = objectMapper.readTree(responseBody);
			JsonNode content = root.get("content");
			if (content != null && content.isArray()) {
				StringBuilder sb = new StringBuilder();
				for (JsonNode block : content) {
					if (block == null || !block.isObject()) {
						continue;
					}
					JsonNode typeNode = block.get("type");
					String type = typeNode == null ? "" : typeNode.asText("");

					// 1) Text-like blocks
					JsonNode text = block.get("text");
					if (text != null && StringUtils.hasText(text.asText())) {
						// Some providers may use "output_text" etc.
						if (!StringUtils.hasText(type) || "text".equals(type) || type.endsWith("text")) {
							sb.append(text.asText());
							continue;
						}
					}

					// 2) JSON-like blocks (provider variants)
					JsonNode jsonNode = block.get("json");
					if (jsonNode != null && !jsonNode.isNull()) {
						sb.append(objectMapper.writeValueAsString(jsonNode));
						continue;
					}

					// 3) Fallback: if block itself looks like a plain object with fields, keep it as JSON
					if (!StringUtils.hasText(type) && block.size() > 0) {
						sb.append(objectMapper.writeValueAsString(block));
					}
				}
				String aggregated = sb.toString();
				if (StringUtils.hasText(aggregated)) {
					return aggregated;
				}
			}

			// Some APIs may respond with a top-level "json" field
			JsonNode json = root.get("json");
			if (json != null && !json.isNull()) {
				return objectMapper.writeValueAsString(json);
			}
			// Fallback: try common field names
			JsonNode text = root.get("text");
			return text != null ? text.asText() : responseBody;
		}
		catch (Exception e) {
			return responseBody;
		}
	}

	private static String buildSystemText(List<Message> messages) {
		if (messages == null || messages.isEmpty()) {
			return "";
		}
		List<String> systemChunks = new ArrayList<>();
		for (Message message : messages) {
			if ("system".equals(resolveRole(message))) {
				String content = extractMessageText(message);
				if (StringUtils.hasText(content)) {
					systemChunks.add(content);
				}
			}
		}
		return String.join("\n\n", systemChunks);
	}

	private static String resolveRole(Message message) {
		if (message == null) {
			return "user";
		}
		String simpleName = message.getClass().getSimpleName().toLowerCase();
		if (simpleName.contains("system")) {
			return "system";
		}
		if (simpleName.contains("assistant")) {
			return "assistant";
		}
		return "user";
	}

	private static String extractMessageText(Message message) {
		if (message == null) {
			return "";
		}

		// Prefer getText() if available (common for Spring AI message types).
		String text = tryInvokeStringGetter(message, "getText");
		if (StringUtils.hasText(text)) {
			return text;
		}
		// Fallback to getContent() if present.
		String content = tryInvokeStringGetter(message, "getContent");
		return content == null ? "" : content;
	}

	private static String tryInvokeStringGetter(Object target, String methodName) {
		try {
			Method method = target.getClass().getMethod(methodName);
			Object value = method.invoke(target);
			return value == null ? "" : String.valueOf(value);
		}
		catch (Exception ignored) {
			return "";
		}
	}

	private static String extractPromptText(Prompt prompt) {
		if (prompt == null) {
			return "";
		}
		// Prefer getContents() when available (varies across Spring AI versions).
		try {
			Method method = prompt.getClass().getMethod("getContents");
			Object value = method.invoke(prompt);
			return value == null ? "" : String.valueOf(value);
		}
		catch (Exception ignored) {
			return prompt.toString();
		}
	}

	private static String normalizePath(String path) {
		if (!StringUtils.hasText(path)) {
			return "v1/messages";
		}
		String trimmed = path.trim();
		if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
			return trimmed;
		}
		while (trimmed.startsWith("/")) {
			trimmed = trimmed.substring(1);
		}
		return trimmed;
	}

	private static String toHexPreview(byte[] bytes, int maxBytes) {
		if (bytes == null || bytes.length == 0 || maxBytes <= 0) {
			return "";
		}
		int n = Math.min(bytes.length, maxBytes);
		StringBuilder sb = new StringBuilder(n * 3);
		for (int i = 0; i < n; i++) {
			int v = bytes[i] & 0xFF;
			if (i > 0) {
				sb.append(' ');
			}
			sb.append(Character.forDigit((v >>> 4) & 0xF, 16));
			sb.append(Character.forDigit(v & 0xF, 16));
		}
		if (bytes.length > n) {
			sb.append(" ...");
		}
		return sb.toString();
	}

}
