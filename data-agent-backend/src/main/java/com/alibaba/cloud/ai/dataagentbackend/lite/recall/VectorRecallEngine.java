package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding.EmbeddingClient;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * 基于 embedding 的向量召回。
 */
public class VectorRecallEngine implements RecallEngine {

	private final EmbeddingClient embeddingClient;

	public VectorRecallEngine(EmbeddingClient embeddingClient) {
		this.embeddingClient = Objects.requireNonNull(embeddingClient, "embeddingClient");
	}

	@Override
	public List<RecallHit> search(String query, List<RecallDocument> documents, RecallOptions options) {
		if (documents == null || documents.isEmpty()) {
			return List.of();
		}
		RecallOptions effectiveOptions = options == null ? RecallOptions.defaults() : options;
		List<Double> queryVector = embeddingClient.embed(query);
		if (queryVector.isEmpty()) {
			return List.of();
		}
		return documents.stream()
			.filter(document -> matchesType(document, effectiveOptions.types()))
			.filter(document -> matchesMetadata(document, effectiveOptions.requiredMetadata()))
			.map(document -> toHit(document, queryVector))
			.filter(hit -> hit.score() > 0)
			.sorted(Comparator.comparingDouble(RecallHit::score).reversed())
			.limit(effectiveOptions.topK())
			.toList();
	}

	private RecallHit toHit(RecallDocument document, List<Double> queryVector) {
		List<Double> vector = RecallEmbeddings.embedding(document);
		if (vector.isEmpty()) {
			return new RecallHit(document, 0, List.of("no-embedding"));
		}
		double similarity = cosineSimilarity(queryVector, vector);
		return new RecallHit(document, similarity, List.of("vector"));
	}

	private static boolean matchesType(RecallDocument document, Set<RecallDocumentType> types) {
		return types == null || types.isEmpty() || types.contains(document.type());
	}

	private static boolean matchesMetadata(RecallDocument document, Map<String, Object> requiredMetadata) {
		if (requiredMetadata == null || requiredMetadata.isEmpty()) {
			return true;
		}
		Map<String, Object> metadata = document.metadata();
		for (Map.Entry<String, Object> entry : requiredMetadata.entrySet()) {
			Object actual = metadata.get(entry.getKey());
			if (actual == null || !actual.equals(entry.getValue())) {
				return false;
			}
		}
		return true;
	}

	static double cosineSimilarity(List<Double> left, List<Double> right) {
		if (left == null || right == null || left.isEmpty() || right.isEmpty() || left.size() != right.size()) {
			return 0;
		}
		double dot = 0;
		double leftNorm = 0;
		double rightNorm = 0;
		for (int i = 0; i < left.size(); i++) {
			double a = left.get(i);
			double b = right.get(i);
			dot += a * b;
			leftNorm += a * a;
			rightNorm += b * b;
		}
		if (leftNorm <= 0 || rightNorm <= 0) {
			return 0;
		}
		return dot / (Math.sqrt(leftNorm) * Math.sqrt(rightNorm));
	}

}
