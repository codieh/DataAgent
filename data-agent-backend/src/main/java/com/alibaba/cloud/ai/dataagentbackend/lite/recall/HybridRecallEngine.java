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
import java.util.Locale;
import java.util.Map;
import java.util.Set;

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

	private final double schemaTableWeight;

	private final double schemaColumnWeight;

	private final double evidenceWeight;

	private final double documentWeight;

	private final double exactMatchBonus;

	public HybridRecallEngine(EmbeddingClient embeddingClient,
			@Value("${search.lite.recall.provider:hybrid}") String provider,
			@Value("${search.lite.recall.vector.weight:0.7}") double vectorWeight,
			@Value("${search.lite.recall.weight.schema-table:1.15}") double schemaTableWeight,
			@Value("${search.lite.recall.weight.schema-column:1.05}") double schemaColumnWeight,
			@Value("${search.lite.recall.weight.evidence:0.95}") double evidenceWeight,
			@Value("${search.lite.recall.weight.document:0.9}") double documentWeight,
			@Value("${search.lite.recall.weight.exact-match-bonus:0.15}") double exactMatchBonus) {
		this.vectorRecallEngine = new VectorRecallEngine(embeddingClient);
		this.provider = provider == null ? "hybrid" : provider.trim().toLowerCase();
		this.vectorWeight = Math.max(0, Math.min(1, vectorWeight));
		this.schemaTableWeight = Math.max(0.1, schemaTableWeight);
		this.schemaColumnWeight = Math.max(0.1, schemaColumnWeight);
		this.evidenceWeight = Math.max(0.1, evidenceWeight);
		this.documentWeight = Math.max(0.1, documentWeight);
		this.exactMatchBonus = Math.max(0, exactMatchBonus);
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
		double maxKeywordScore = keywordHits.stream().mapToDouble(RecallHit::score).max().orElse(0);
		Set<String> queryTokens = RecallTokenizers.tokenizeMixed(query);
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
			.map(fusedHit -> fusedHit.toRecallHit(vectorWeight, maxKeywordScore, query, queryTokens))
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
						Object keywordNormalized = hit.document().metadata().get("_keywordNormalized");
						Object vectorScore = hit.document().metadata().get("_vectorScore");
						Object typeWeight = hit.document().metadata().get("_typeWeight");
						Object exactBonus = hit.document().metadata().get("_exactMatchBonus");
						return "%s(keyword=%s, keywordNorm=%s, vector=%s, typeWeight=%s, exactBonus=%s, fused=%.4f)".formatted(
								hit.document().id(), keywordScore == null ? "-" : keywordScore,
								keywordNormalized == null ? "-" : keywordNormalized, vectorScore == null ? "-" : vectorScore,
								typeWeight == null ? "-" : typeWeight, exactBonus == null ? "-" : exactBonus, hit.score());
					})
					.toList()
					.toString();
		log.info("hybrid recall：provider={}, queryLen={}, vectorWeight={}, typeWeights=[table:{},column:{},evidence:{},document:{}], hits={}",
				provider, query == null ? 0 : query.length(), vectorWeight, schemaTableWeight, schemaColumnWeight,
				evidenceWeight, documentWeight, summary);
	}

	private final class FusedHit {

		private final RecallDocument document;

		private double keywordScore;

		private double vectorScore;

		private FusedHit(RecallDocument document) {
			this.document = document;
		}

		private RecallHit toRecallHit(double vectorWeight, double maxKeywordScore, String query, Set<String> queryTokens) {
			double keywordWeight = 1.0 - vectorWeight;
			double keywordNormalized = maxKeywordScore <= 0 ? 0 : keywordScore / maxKeywordScore;
			double typeWeight = resolveTypeWeight(document.type());
			double exactBonus = resolveExactMatchBonus(document, query, queryTokens);
			double fusedScore = (keywordNormalized * keywordWeight + vectorScore * vectorWeight) * typeWeight + exactBonus;
			List<String> reasons = new ArrayList<>();
			if (keywordScore > 0) {
				reasons.add("keyword");
			}
			if (vectorScore > 0) {
				reasons.add("vector");
			}
			if (exactBonus > 0) {
				reasons.add("exact-match");
			}
			Map<String, Object> metadata = new LinkedHashMap<>(document.metadata());
			metadata.put("_keywordScore", keywordScore);
			metadata.put("_keywordNormalized", keywordNormalized);
			metadata.put("_vectorScore", vectorScore);
			metadata.put("_typeWeight", typeWeight);
			metadata.put("_exactMatchBonus", exactBonus);
			RecallDocument traced = new RecallDocument(document.id(), document.type(), document.title(), document.content(),
					metadata);
			return new RecallHit(traced, fusedScore, reasons);
		}

	}

	private double resolveTypeWeight(RecallDocumentType type) {
		if (type == null) {
			return 1.0;
		}
		return switch (type) {
			case SCHEMA_TABLE -> schemaTableWeight;
			case SCHEMA_COLUMN -> schemaColumnWeight;
			case EVIDENCE -> evidenceWeight;
			case DOCUMENT -> documentWeight;
		};
	}

	private double resolveExactMatchBonus(RecallDocument document, String query, Set<String> queryTokens) {
		if (document == null || query == null || query.isBlank()) {
			return 0;
		}
		String lowerQuery = query.toLowerCase(Locale.ROOT);
		if (containsExact(lowerQuery, document.title())) {
			return exactMatchBonus;
		}
		Object tableName = document.metadata().get("tableName");
		if (tableName instanceof String table && containsExact(lowerQuery, table)) {
			return exactMatchBonus;
		}
		Object columnName = document.metadata().get("columnName");
		if (columnName instanceof String column && containsExact(lowerQuery, column)) {
			return exactMatchBonus;
		}
		return queryTokens.stream().anyMatch(token -> containsExact(document.title().toLowerCase(Locale.ROOT), token))
				? exactMatchBonus / 2.0 : 0;
	}

	private boolean containsExact(String fullText, String part) {
		if (fullText == null || part == null || part.isBlank()) {
			return false;
		}
		return fullText.contains(part.trim().toLowerCase(Locale.ROOT));
	}

}
