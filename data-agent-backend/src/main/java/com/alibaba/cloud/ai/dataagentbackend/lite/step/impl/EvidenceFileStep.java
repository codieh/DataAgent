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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * 证据召回（Evidence）阶段：v1 文件检索实现。
 * <p>
 * 数据来源：{@code classpath:evidence/evidence.json}
 * <p>
 * 召回策略（v1 简化版）：对 query 做非常粗糙的“分词 + 包含匹配打分”，取 topK。
 * <p>
 * 注意：
 * <ul>
 *   <li>这不是生产级检索（无 BM25/无向量相似度）。</li>
 *   <li>当前 tokenize/score 对中文效果较弱；后续要升级检索时，可替换 {@link #tokenize(String)} 与 {@link #score(EvidenceItem, Set)}。</li>
 * </ul>
 */
@Component
@Order(20)
@ConditionalOnProperty(name = "search.lite.evidence.provider", havingValue = "file", matchIfMissing = true)
public class EvidenceFileStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(EvidenceFileStep.class);

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

		List<EvidenceItem> all = evidenceRepository.listAll();
		if (all == null || all.isEmpty()) {
			log.warn("evidence 为空：threadId={}, topK={}", context.threadId(), topK);
		}
		else {
			log.debug("evidence 开始召回：threadId={}, queryLen={}, tokens={}, topK={}, total={}", context.threadId(),
					query == null ? 0 : query.length(), tokens.size(), topK, all.size());
		}

		List<ScoredEvidence> scored = (all == null ? List.<EvidenceItem>of() : all).stream()
			.map(item -> new ScoredEvidence(item, score(item, tokens)))
			.filter(se -> se.score > 0)
			.sorted(Comparator.<ScoredEvidence>comparingDouble(se -> se.score).reversed())
			.limit(topK)
			.toList();

		List<EvidenceItem> selected = scored.stream().map(se -> se.item).toList();
		log.debug("evidence 召回完成：threadId={}, selected={}", context.threadId(), selected.stream()
			.map(EvidenceItem::id)
			.limit(10)
			.toList());
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
		// v1：按“非字母/数字”切分；对中文不友好，后续可替换为中文分词或向量召回。
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
		// 如果 evidence.json 中自带了 score，则作为一个很小的先验加权。
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

