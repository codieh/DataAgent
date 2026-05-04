package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 轻量 BM25 召回，用来增强表名、列名、业务术语等 lexical 命中能力。
 */
@Component
public class Bm25RecallEngine implements RecallEngine {

	private static final Pattern SPLIT = Pattern.compile("[^\\p{IsAlphabetic}\\p{IsDigit}]+");

	private static final Pattern CJK = Pattern.compile("[\\p{IsHan}]{2,}");

	private final double k1;

	private final double b;

	private final double titleBoost;

	public Bm25RecallEngine(@Value("${search.lite.recall.bm25.k1:1.2}") double k1,
			@Value("${search.lite.recall.bm25.b:0.75}") double b,
			@Value("${search.lite.recall.bm25.title-boost:2.0}") double titleBoost) {
		this.k1 = Math.max(0.1, k1);
		this.b = Math.max(0, Math.min(1, b));
		this.titleBoost = Math.max(1.0, titleBoost);
	}

	@Override
	public List<RecallHit> search(String query, List<RecallDocument> documents, RecallOptions options) {
		if (documents == null || documents.isEmpty()) {
			return List.of();
		}
		RecallOptions effectiveOptions = options == null ? RecallOptions.defaults() : options;
		Map<String, Integer> queryTerms = countTerms(query);
		if (queryTerms.isEmpty()) {
			return List.of();
		}
		List<DocumentStats> stats = documents.stream()
			.filter(document -> matchesType(document, effectiveOptions.types()))
			.filter(document -> RecallMetadataMatcher.matches(document, effectiveOptions.requiredMetadata()))
			.map(this::buildStats)
			.toList();
		if (stats.isEmpty()) {
			return List.of();
		}
		double averageLength = stats.stream().mapToDouble(DocumentStats::length).average().orElse(1.0);
		Map<String, Integer> documentFrequency = computeDocumentFrequency(stats, queryTerms.keySet());
		return stats.stream()
			.map(stat -> score(stat, queryTerms, documentFrequency, averageLength, stats.size()))
			.filter(hit -> hit.score() > 0)
			.sorted(Comparator.comparingDouble(RecallHit::score).reversed())
			.limit(effectiveOptions.topK())
			.toList();
	}

	private static boolean matchesType(RecallDocument document, Set<RecallDocumentType> types) {
		return types == null || types.isEmpty() || types.contains(document.type());
	}

	private DocumentStats buildStats(RecallDocument document) {
		Map<String, Double> frequencies = new LinkedHashMap<>();
		double length = 0;
		for (String token : tokenizeWithFrequency(document.title())) {
			frequencies.merge(token, titleBoost, Double::sum);
			length += titleBoost;
		}
		for (String token : tokenizeWithFrequency(document.content())) {
			frequencies.merge(token, 1.0, Double::sum);
			length += 1.0;
		}
		if (length <= 0) {
			length = 1.0;
		}
		return new DocumentStats(document, frequencies, length);
	}

	private RecallHit score(DocumentStats stats, Map<String, Integer> queryTerms, Map<String, Integer> documentFrequency,
			double averageLength, int documentCount) {
		double bm25Score = 0;
		List<String> matchedTerms = new ArrayList<>();
		for (Map.Entry<String, Integer> entry : queryTerms.entrySet()) {
			String term = entry.getKey();
			double tf = stats.frequencies().getOrDefault(term, 0.0);
			if (tf <= 0) {
				continue;
			}
			matchedTerms.add(term);
			double df = documentFrequency.getOrDefault(term, 0);
			double idf = Math.log1p((documentCount - df + 0.5) / (df + 0.5));
			double denominator = tf + k1 * (1 - b + b * stats.length() / Math.max(averageLength, 1.0));
			double queryBoost = 1.0 + Math.max(0, entry.getValue() - 1) * 0.2;
			bm25Score += idf * ((tf * (k1 + 1)) / Math.max(denominator, 1e-9)) * queryBoost;
		}
		Map<String, Object> metadata = new LinkedHashMap<>(stats.document().metadata());
		metadata.put("_bm25Score", bm25Score);
		metadata.put("_bm25MatchedTerms", matchedTerms);
		metadata.put("_bm25Length", stats.length());
		RecallDocument traced = new RecallDocument(stats.document().id(), stats.document().type(), stats.document().title(),
				stats.document().content(), metadata);
		return new RecallHit(traced, bm25Score, matchedTerms);
	}

	private static Map<String, Integer> computeDocumentFrequency(List<DocumentStats> stats, Set<String> queryTerms) {
		Map<String, Integer> frequency = new LinkedHashMap<>();
		for (String term : queryTerms) {
			int df = 0;
			for (DocumentStats stat : stats) {
				if (stat.frequencies().containsKey(term)) {
					df++;
				}
			}
			frequency.put(term, df);
		}
		return frequency;
	}

	private static Map<String, Integer> countTerms(String text) {
		Map<String, Integer> counts = new LinkedHashMap<>();
		for (String token : tokenizeWithFrequency(text)) {
			counts.merge(token, 1, Integer::sum);
		}
		return counts;
	}

	private static List<String> tokenizeWithFrequency(String text) {
		if (text == null || text.isBlank()) {
			return List.of();
		}
		String normalized = text.toLowerCase(Locale.ROOT);
		List<String> tokens = new ArrayList<>();
		SPLIT.splitAsStream(normalized)
			.filter(token -> token != null && !token.isBlank())
			.filter(token -> token.length() >= 2)
			.forEach(tokens::add);
		Matcher matcher = CJK.matcher(text);
		while (matcher.find()) {
			String segment = matcher.group();
			if (segment == null || segment.isBlank()) {
				continue;
			}
			String trimmed = segment.trim();
			if (trimmed.length() < 2) {
				continue;
			}
			tokens.add(trimmed);
			for (int i = 0; i < trimmed.length() - 1; i++) {
				tokens.add(trimmed.substring(i, i + 2));
			}
		}
		return tokens;
	}

	private record DocumentStats(RecallDocument document, Map<String, Double> frequencies, double length) {
	}

}
