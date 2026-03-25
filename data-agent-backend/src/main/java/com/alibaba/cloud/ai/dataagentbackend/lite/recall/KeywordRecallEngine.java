package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.springframework.stereotype.Component;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 第一版轻量召回引擎。
 *
 * <p>
 * 当前仅使用关键词命中做打分，目标是先统一 schema / evidence 的召回入口，
 * 后续再逐步升级为向量召回或混合召回。
 * </p>
 */
@Component
public class KeywordRecallEngine implements RecallEngine {

	@Override
	public List<RecallHit> search(String query, List<RecallDocument> documents, RecallOptions options) {
		if (documents == null || documents.isEmpty()) {
			return List.of();
		}

		RecallOptions effectiveOptions = options == null ? RecallOptions.defaults() : options;
		Set<String> tokens = RecallTokenizers.tokenizeMixed(query);
		if (tokens.isEmpty()) {
			return List.of();
		}

		return documents.stream()
			.filter(document -> matchesType(document, effectiveOptions.types()))
			.filter(document -> matchesMetadata(document, effectiveOptions.requiredMetadata()))
			.map(document -> scoreDocument(document, tokens))
			.filter(hit -> hit.score() > 0)
			.sorted(Comparator.comparingDouble(RecallHit::score).reversed())
			.limit(effectiveOptions.topK())
			.toList();
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

	private static RecallHit scoreDocument(RecallDocument document, Set<String> tokens) {
		String lowerTitle = document.title().toLowerCase(Locale.ROOT);
		String lowerContent = document.content().toLowerCase(Locale.ROOT);
		double score = 0;
		List<String> matchedTerms = tokens.stream().filter(token -> {
			String lowerToken = token.toLowerCase(Locale.ROOT);
			boolean titleMatched = lowerTitle.contains(lowerToken);
			boolean contentMatched = lowerContent.contains(lowerToken);
			return titleMatched || contentMatched;
		}).collect(Collectors.toList());

		for (String matchedTerm : matchedTerms) {
			String lowerToken = matchedTerm.toLowerCase(Locale.ROOT);
			if (lowerTitle.contains(lowerToken)) {
				score += 2.0;
			}
			if (lowerContent.contains(lowerToken)) {
				score += 1.0;
			}
		}
		return new RecallHit(document, score, matchedTerms);
	}

}
