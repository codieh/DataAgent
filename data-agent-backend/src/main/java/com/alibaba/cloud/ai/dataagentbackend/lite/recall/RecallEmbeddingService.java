package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding.EmbeddingClient;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding.EmbeddingProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * 为 recall 文档补充 embedding。
 */
@Service
public class RecallEmbeddingService {

	private static final Logger log = LoggerFactory.getLogger(RecallEmbeddingService.class);

	private final EmbeddingClient embeddingClient;

	private final EmbeddingProperties embeddingProperties;

	private final String provider;

	public RecallEmbeddingService(EmbeddingClient embeddingClient, EmbeddingProperties embeddingProperties,
			@Value("${search.lite.recall.provider:hybrid}") String provider) {
		this.embeddingClient = Objects.requireNonNull(embeddingClient, "embeddingClient");
		this.embeddingProperties = Objects.requireNonNull(embeddingProperties, "embeddingProperties");
		this.provider = provider == null ? "hybrid" : provider.trim().toLowerCase();
	}

	public boolean vectorEnabled() {
		return "vector".equals(provider) || "hybrid".equals(provider);
	}

	public List<RecallDocument> ensureEmbeddings(List<RecallDocument> documents) {
		if (!vectorEnabled() || documents == null || documents.isEmpty()) {
			return documents == null ? List.of() : documents;
		}
		long start = System.currentTimeMillis();
		List<RecallDocument> enriched = new ArrayList<>(documents.size());
		List<RecallDocument> missing = documents.stream().filter(document -> !RecallEmbeddings.hasEmbedding(document)).toList();
		List<List<Double>> vectors = embeddingClient.embedAll(missing.stream().map(RecallDocument::searchableText).toList());

		int vectorIndex = 0;
		for (RecallDocument document : documents) {
			if (RecallEmbeddings.hasEmbedding(document)) {
				enriched.add(document);
				continue;
			}
			List<Double> vector = vectorIndex < vectors.size() ? vectors.get(vectorIndex) : List.of();
			vectorIndex++;
			enriched.add(RecallEmbeddings.withEmbedding(document, vector, embeddingProperties.model()));
		}
		log.info("embedding 补全：provider={}, model={}, totalDocs={}, missingDocs={}, generatedVectors={}, tookMs={}",
				provider, embeddingProperties.model(), documents.size(), missing.size(), vectors.size(),
				System.currentTimeMillis() - start);
		return List.copyOf(enriched);
	}

}
