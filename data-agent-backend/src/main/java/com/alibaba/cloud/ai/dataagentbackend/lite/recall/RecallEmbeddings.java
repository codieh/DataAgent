package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Recall 内部 embedding 元数据工具。
 */
public final class RecallEmbeddings {

	public static final String KEY_EMBEDDING = "_embedding";

	private static final String KEY_MODEL = "_embeddingModel";

	private RecallEmbeddings() {
	}

	public static boolean hasEmbedding(RecallDocument document) {
		return !embedding(document).isEmpty();
	}

	@SuppressWarnings("unchecked")
	public static List<Double> embedding(RecallDocument document) {
		if (document == null || document.metadata() == null) {
			return List.of();
		}
		Object raw = document.metadata().get(KEY_EMBEDDING);
		if (raw instanceof List<?> list) {
			return list.stream().filter(Number.class::isInstance).map(Number.class::cast).map(Number::doubleValue).toList();
		}
		return List.of();
	}

	public static RecallDocument withEmbedding(RecallDocument document, List<Double> vector, String model) {
		Map<String, Object> metadata = new LinkedHashMap<>(document.metadata());
		metadata.put(KEY_EMBEDDING, vector == null ? List.of() : List.copyOf(vector));
		if (model != null && !model.isBlank()) {
			metadata.put(KEY_MODEL, model.trim());
		}
		return new RecallDocument(document.id(), document.type(), document.title(), document.content(), metadata);
	}

	public static Map<String, Object> publicMetadata(Map<String, Object> metadata) {
		if (metadata == null || metadata.isEmpty()) {
			return Map.of();
		}
		Map<String, Object> copy = new LinkedHashMap<>(metadata);
		copy.remove(KEY_EMBEDDING);
		copy.remove(KEY_MODEL);
		return copy;
	}

}
