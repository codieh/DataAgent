package com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding;

import java.util.List;

/**
 * Embedding 调用抽象。
 */
public interface EmbeddingClient {

	List<Double> embed(String text);

	default List<List<Double>> embedAll(List<String> texts) {
		if (texts == null || texts.isEmpty()) {
			return List.of();
		}
		return texts.stream().map(this::embed).toList();
	}

}
