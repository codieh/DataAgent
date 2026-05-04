package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * 轻量 reranker：
 * 在不引入额外 cross-encoder 服务之前，先用 query-aware 特征做最终排序收敛。
 */
@Component
public class LightweightRecallReranker implements RecallReranker {

	private final double baseScoreWeight;

	private final double coverageWeight;

	private final double exactMatchBoost;

	public LightweightRecallReranker(@Value("${search.lite.recall.rerank.base-score-weight:0.7}") double baseScoreWeight,
			@Value("${search.lite.recall.rerank.coverage-weight:0.3}") double coverageWeight,
			@Value("${search.lite.recall.rerank.exact-match-boost:0.12}") double exactMatchBoost) {
		this.baseScoreWeight = Math.max(0.1, baseScoreWeight);
		this.coverageWeight = Math.max(0, coverageWeight);
		this.exactMatchBoost = Math.max(0, exactMatchBoost);
	}

	@Override
	public List<RecallHit> rerank(String query, List<RecallHit> candidates, int topK) {
		if (candidates == null || candidates.isEmpty()) {
			return List.of();
		}
		Set<String> queryTokens = RecallTokenizers.tokenizeMixed(query);
		int effectiveTopK = topK <= 0 ? candidates.size() : topK;
		return candidates.stream()
			.map(hit -> rerankHit(hit, query, queryTokens))
			.sorted(Comparator.comparingDouble(RecallHit::score).reversed())
			.limit(effectiveTopK)
			.toList();
	}

	private RecallHit rerankHit(RecallHit hit, String query, Set<String> queryTokens) {
		RecallDocument document = hit.document();
		String searchableText = document.searchableText().toLowerCase(Locale.ROOT);
		long matchedTokenCount = queryTokens.stream().filter(searchableText::contains).count();
		double coverage = queryTokens.isEmpty() ? 0 : matchedTokenCount / (double) queryTokens.size();
		double exactBonus = resolveExactBonus(query, document);
		double rerankScore = hit.score() * baseScoreWeight + coverage * coverageWeight + exactBonus;
		Map<String, Object> metadata = new LinkedHashMap<>(document.metadata());
		metadata.put("_rerankScore", rerankScore);
		metadata.put("_rerankCoverage", coverage);
		metadata.put("_rerankExactBonus", exactBonus);
		RecallDocument traced = new RecallDocument(document.id(), document.type(), document.title(), document.content(), metadata);
		return new RecallHit(traced, rerankScore, hit.matchedTerms());
	}

	private double resolveExactBonus(String query, RecallDocument document) {
		if (query == null || query.isBlank() || document == null) {
			return 0;
		}
		String lowerQuery = query.toLowerCase(Locale.ROOT);
		if (containsExact(lowerQuery, document.title())) {
			return exactMatchBoost;
		}
		Object tableName = document.metadata().get("tableName");
		if (tableName instanceof String table && containsExact(lowerQuery, table)) {
			return exactMatchBoost;
		}
		Object columnName = document.metadata().get("columnName");
		if (columnName instanceof String column && containsExact(lowerQuery, column)) {
			return exactMatchBoost;
		}
		return 0;
	}

	private boolean containsExact(String fullText, String part) {
		if (fullText == null || part == null || part.isBlank()) {
			return false;
		}
		return fullText.contains(part.trim().toLowerCase(Locale.ROOT));
	}

}
