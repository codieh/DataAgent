package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding.EmbeddingClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 参考 management 的混合检索思路：向量检索 + 关键词检索，再做分数融合。
 */
@Component
@Primary
public class HybridRecallEngine implements RecallEngine {

	private static final Logger log = LoggerFactory.getLogger(HybridRecallEngine.class);

	private final KeywordRecallEngine keywordRecallEngine = new KeywordRecallEngine();

	private final VectorRecallEngine vectorRecallEngine;

	private final String provider;

	private final double vectorWeight;

	public HybridRecallEngine(EmbeddingClient embeddingClient,
			@Value("${search.lite.recall.provider:hybrid}") String provider,
			@Value("${search.lite.recall.vector.weight:0.7}") double vectorWeight) {
		this.vectorRecallEngine = new VectorRecallEngine(embeddingClient);
		this.provider = provider == null ? "hybrid" : provider.trim().toLowerCase();
		this.vectorWeight = Math.max(0, Math.min(1, vectorWeight));
	}

	@Override
	public List<RecallHit> search(String query, List<RecallDocument> documents, RecallOptions options) {
		return switch (provider) {
			case "keyword" -> keywordRecallEngine.search(query, documents, options);
			case "vector" -> vectorRecallEngine.search(query, documents, options);
			default -> hybridSearch(query, documents, options);
		};
	}

	private List<RecallHit> hybridSearch(String query, List<RecallDocument> documents, RecallOptions options) {
		List<RecallHit> keywordHits = keywordRecallEngine.search(query, documents, options);
		List<RecallHit> vectorHits = vectorRecallEngine.search(query, documents, options);
		if (vectorHits.isEmpty()) {
			return keywordHits;
		}
		Map<String, FusedHit> fused = new LinkedHashMap<>();
		for (RecallHit hit : keywordHits) {
			fused.computeIfAbsent(hit.document().id(), id -> new FusedHit(hit.document()))
				.keywordScore = hit.score();
		}
		for (RecallHit hit : vectorHits) {
			fused.computeIfAbsent(hit.document().id(), id -> new FusedHit(hit.document()))
				.vectorScore = hit.score();
		}
		int topK = options == null ? RecallOptions.defaults().topK() : options.topK();
		List<RecallHit> results = fused.values().stream()
			.map(fusedHit -> fusedHit.toRecallHit(vectorWeight))
			.sorted(Comparator.comparingDouble(RecallHit::score).reversed())
			.limit(topK)
			.toList();
		logHybridScores(query, results);
		return results;
	}

	private void logHybridScores(String query, List<RecallHit> hits) {
		if (!log.isInfoEnabled()) {
			return;
		}
		String summary = hits == null || hits.isEmpty() ? "(empty)"
				: hits.stream()
					.limit(5)
					.map(hit -> {
						Object keywordScore = hit.document().metadata().get("_keywordScore");
						Object vectorScore = hit.document().metadata().get("_vectorScore");
						return "%s(keyword=%s, vector=%s, fused=%.4f)".formatted(hit.document().id(),
								keywordScore == null ? "-" : keywordScore, vectorScore == null ? "-" : vectorScore,
								hit.score());
					})
					.toList()
					.toString();
		log.info("hybrid recall：provider={}, queryLen={}, vectorWeight={}, hits={}", provider,
				query == null ? 0 : query.length(), vectorWeight, summary);
	}

	private static final class FusedHit {

		private final RecallDocument document;

		private double keywordScore;

		private double vectorScore;

		private FusedHit(RecallDocument document) {
			this.document = document;
		}

		private RecallHit toRecallHit(double vectorWeight) {
			double keywordWeight = 1.0 - vectorWeight;
			double fusedScore = keywordScore * keywordWeight + vectorScore * vectorWeight;
			List<String> reasons = new ArrayList<>();
			if (keywordScore > 0) {
				reasons.add("keyword");
			}
			if (vectorScore > 0) {
				reasons.add("vector");
			}
			Map<String, Object> metadata = new LinkedHashMap<>(document.metadata());
			metadata.put("_keywordScore", keywordScore);
			metadata.put("_vectorScore", vectorScore);
			RecallDocument traced = new RecallDocument(document.id(), document.type(), document.title(), document.content(),
					metadata);
			return new RecallHit(traced, fusedScore, reasons);
		}

	}

}
