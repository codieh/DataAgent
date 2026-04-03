package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class SearchLiteGraphMessageNormalizer {

	private final ObjectMapper objectMapper;

	public SearchLiteGraphMessageNormalizer(ObjectMapper objectMapper) {
		this.objectMapper = objectMapper;
	}

	public List<SearchLiteMessage> normalizeMessages(List<?> rawMessages) {
		if (rawMessages == null || rawMessages.isEmpty()) {
			return List.of();
		}
		List<SearchLiteMessage> normalized = new ArrayList<>(rawMessages.size());
		for (Object rawMessage : rawMessages) {
			SearchLiteMessage message = normalizeMessage(rawMessage);
			if (message != null) {
				normalized.add(message);
			}
		}
		return normalized;
	}

	public SearchLiteMessage normalizeMessage(Object rawMessage) {
		if (rawMessage == null) {
			return null;
		}
		SearchLiteMessage message = rawMessage instanceof SearchLiteMessage searchLiteMessage ? searchLiteMessage
				: objectMapper.convertValue(rawMessage, SearchLiteMessage.class);
		Object normalizedPayload = normalizePayload(message.payload());
		return new SearchLiteMessage(message.threadId(), message.stage(), message.type(), message.chunk(), normalizedPayload,
				message.done(), message.error(), message.seq(), message.timestamp() == null ? Instant.now() : message.timestamp());
	}

	private Object normalizePayload(Object payload) {
		if (payload == null) {
			return null;
		}
		if (payload instanceof String || payload instanceof Number || payload instanceof Boolean) {
			return payload;
		}
		if (payload instanceof Map<?, ?> map) {
			LinkedHashMap<String, Object> normalized = new LinkedHashMap<>();
			for (Map.Entry<?, ?> entry : map.entrySet()) {
				normalized.put(String.valueOf(entry.getKey()), normalizePayload(entry.getValue()));
			}
			return normalized;
		}
		if (payload instanceof List<?> list) {
			List<Object> normalized = new ArrayList<>(list.size());
			for (Object item : list) {
				normalized.add(normalizePayload(item));
			}
			return normalized;
		}
		try {
			return objectMapper.readValue(objectMapper.writeValueAsBytes(payload), Object.class);
		}
		catch (Exception e) {
			try {
				Map<?, ?> converted = objectMapper.convertValue(payload, Map.class);
				return normalizePayload(converted);
			}
			catch (Exception ignored) {
				try {
					return objectMapper.convertValue(objectMapper.valueToTree(payload), Object.class);
				}
				catch (Exception ignoredAgain) {
					return String.valueOf(payload);
				}
			}
		}
	}

}
