package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.evidence.EvidenceRepository;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.EvidenceRecallResult;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallService;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;
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

	private final EvidenceRepository evidenceRepository;

	private final RecallService recallService;

	private final int topK;

	public EvidenceFileStep(EvidenceRepository evidenceRepository, RecallService recallService,
			@Value("${search.lite.evidence.top-k:5}") int topK) {
		this.evidenceRepository = Objects.requireNonNull(evidenceRepository, "evidenceRepository");
		this.recallService = Objects.requireNonNull(recallService, "recallService");
		this.topK = Math.max(1, topK);
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.EVIDENCE;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		String query = state.getQuery();
		List<EvidenceItem> all = evidenceRepository.listAll();
		if (all == null || all.isEmpty()) {
			log.warn("evidence 为空：threadId={}, topK={}", context.threadId(), topK);
		}
		else {
			log.debug("evidence 开始召回：threadId={}, queryLen={}, topK={}, total={}", context.threadId(),
					query == null ? 0 : query.length(), topK, all.size());
		}

		EvidenceRecallResult recallResult = recallService.recallEvidence(query, all, topK);
		List<EvidenceItem> selected = recallResult.items();
		log.debug("evidence 召回完成：threadId={}, selected={}", context.threadId(), selected.stream()
			.map(EvidenceItem::id)
			.limit(10)
			.toList());
		state.setEvidences(selected);
		state.setEvidenceText(recallResult.promptText());

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

	private static String safe(String s) {
		return s == null ? "" : s.trim();
	}

}

