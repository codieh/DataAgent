package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.evidence.EvidenceRepository;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import java.time.Duration;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
@Order(20)
@ConditionalOnProperty(name = "search.lite.evidence.provider", havingValue = "file", matchIfMissing = true)
public class EvidenceFileStep implements SearchLiteStep {

	private static final Pattern SPLIT = Pattern.compile("[^\\p{IsAlphabetic}\\p{IsDigit}]+");

	private final EvidenceRepository evidenceRepository;

	private final int topK;

	public EvidenceFileStep(EvidenceRepository evidenceRepository,
			@Value("${search.lite.evidence.top-k:5}") int topK) {
		this.evidenceRepository = Objects.requireNonNull(evidenceRepository, "evidenceRepository");
		this.topK = Math.max(1, topK);
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.EVIDENCE;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		String query = state.getQuery();
		Set<String> tokens = tokenize(query);

		List<ScoredEvidence> scored = evidenceRepository.listAll()
			.stream()
			.map(item -> new ScoredEvidence(item, score(item, tokens)))
			.filter(se -> se.score > 0)
			.sorted(Comparator.<ScoredEvidence>comparingDouble(se -> se.score).reversed())
			.limit(topK)
			.toList();

		List<EvidenceItem> selected = scored.stream().map(se -> se.item).toList();
		state.setEvidences(selected);
		state.setEvidenceText(formatForPrompt(selected));

		Flux<SearchLiteMessage> intro = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在召回证据...", null),
					SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
							"已找到 " + selected.size() + " 条相关证据。", null))
			.delayElements(Duration.ofMillis(80));

		Flux<SearchLiteMessage> snippets = Flux.fromIterable(selected)
			.concatMap(item -> Flux.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
					"[" + safe(item.title()) + "] " + safe(item.snippet()), null)).delayElements(Duration.ofMillis(50)));

		Flux<SearchLiteMessage> payload = Flux.just(SearchLiteMessages.message(context, stage(),
				SearchLiteMessageType.JSON, null, Map.of("evidences", selected)));

		return new SearchLiteStepResult(intro.concatWith(snippets).concatWith(payload), Mono.just(state));
	}

	private static Set<String> tokenize(String text) {
		if (text == null || text.isBlank()) {
			return Set.of();
		}
		return SPLIT.splitAsStream(text.toLowerCase(Locale.ROOT))
			.filter(s -> s != null && !s.isBlank())
			.filter(s -> s.length() >= 2)
			.collect(Collectors.toSet());
	}

	private static double score(EvidenceItem item, Set<String> tokens) {
		if (item == null || tokens.isEmpty()) {
			return 0;
		}
		String haystack = (safe(item.title()) + " " + safe(item.snippet())).toLowerCase(Locale.ROOT);
		double score = 0;
		for (String token : tokens) {
			if (haystack.contains(token)) {
				score += 1.0;
			}
		}
		// small prior from existing score if provided
		if (item.score() != null) {
			score += Math.max(0, Math.min(1.0, item.score())) * 0.5;
		}
		return score;
	}

	private static String formatForPrompt(List<EvidenceItem> items) {
		if (items == null || items.isEmpty()) {
			return "(无证据)";
		}
		StringBuilder sb = new StringBuilder();
		for (int i = 0; i < items.size(); i++) {
			EvidenceItem item = items.get(i);
			sb.append("[证据").append(i + 1).append("] ");
			sb.append(safe(item.title())).append(": ");
			sb.append(safe(item.snippet()));
			sb.append("\n");
		}
		return sb.toString().trim();
	}

	private static String safe(String s) {
		return s == null ? "" : s.trim();
	}

	private record ScoredEvidence(EvidenceItem item, double score) {
	}

}

