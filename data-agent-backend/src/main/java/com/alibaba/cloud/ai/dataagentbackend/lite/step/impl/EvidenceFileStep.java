package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.knowledge.KnowledgeContextFormatter;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.evidence.EvidenceRepository;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.DocumentRecallResult;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.DocumentRepository;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.EvidenceQueryRewriteService;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.EvidenceRecallResult;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocument;
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
import reactor.core.scheduler.Schedulers;

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

	private final DocumentRepository documentRepository;

	private final RecallService recallService;

	private final EvidenceQueryRewriteService evidenceQueryRewriteService;

	private final KnowledgeContextFormatter knowledgeContextFormatter;

	private final int topK;

	private final int documentTopK;

	public EvidenceFileStep(EvidenceRepository evidenceRepository, DocumentRepository documentRepository, RecallService recallService,
			EvidenceQueryRewriteService evidenceQueryRewriteService, KnowledgeContextFormatter knowledgeContextFormatter,
			@Value("${search.lite.evidence.top-k:5}") int topK,
			@Value("${search.lite.document.top-k:3}") int documentTopK) {
		this.evidenceRepository = Objects.requireNonNull(evidenceRepository, "evidenceRepository");
		this.documentRepository = Objects.requireNonNull(documentRepository, "documentRepository");
		this.recallService = Objects.requireNonNull(recallService, "recallService");
		this.evidenceQueryRewriteService = Objects.requireNonNull(evidenceQueryRewriteService, "evidenceQueryRewriteService");
		this.knowledgeContextFormatter = Objects.requireNonNull(knowledgeContextFormatter, "knowledgeContextFormatter");
		this.topK = Math.max(1, topK);
		this.documentTopK = Math.max(1, documentTopK);
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.EVIDENCE;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		Mono<EvidenceRun> runMono = Mono.fromCallable(() -> buildEvidenceRun(context, state)).subscribeOn(Schedulers.boundedElastic())
			.cache();

		Flux<SearchLiteMessage> messages = runMono.flatMapMany(run -> {
			Flux<SearchLiteMessage> intro = Flux
				.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在召回证据...", null),
						SearchLiteMessages.message(context, stage(), SearchLiteMessageType.JSON, null,
								Map.of("originalQuery", safe(run.originalQuery()), "rewrittenQuery", safe(run.rewrittenQuery()))),
						SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
								"已找到 " + run.selected().size() + " 条相关证据，并补充 " + run.documentCount() + " 条文档片段。", null))
				.delayElements(Duration.ofMillis(80));

			Flux<SearchLiteMessage> snippets = Flux.fromIterable(run.selected())
				.concatMap(item -> Flux.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
						"[" + safe(item.title()) + "] " + safe(item.snippet()), null)).delayElements(Duration.ofMillis(50)));

			Flux<SearchLiteMessage> payload = Flux.just(SearchLiteMessages.message(context, stage(),
					SearchLiteMessageType.JSON, null,
					Map.of("evidences", run.selected(), "documents", run.documentSummaries(),
							"rewrittenQuery", safe(run.rewrittenQuery()))));
			return intro.concatWith(snippets).concatWith(payload);
		});

		Mono<SearchLiteState> updated = runMono.map(EvidenceRun::state);
		return new SearchLiteStepResult(messages, updated);
	}

	private static String safe(String s) {
		return s == null ? "" : s.trim();
	}

	private EvidenceRun buildEvidenceRun(SearchLiteContext context, SearchLiteState state) {
		String originalQuery = state.getQuery();
		String rewrittenQuery = evidenceQueryRewriteService.rewrite(originalQuery);
		state.setEvidenceRewriteQuery(rewrittenQuery);
		List<EvidenceItem> all = evidenceRepository.listAll();
		if (all == null || all.isEmpty()) {
			log.warn("evidence 为空：threadId={}, topK={}", context.threadId(), topK);
		}
		else {
			log.info("evidence 召回准备：threadId={}, originalQueryLen={}, rewriteQueryLen={}, topK={}, total={}", context.threadId(),
					originalQuery == null ? 0 : originalQuery.length(), rewrittenQuery == null ? 0 : rewrittenQuery.length(), topK, all.size());
		}

		EvidenceRecallResult recallResult = recallService.recallEvidence(rewrittenQuery, all, topK);
		DocumentRecallResult documentRecallResult = recallService.recallDocuments(rewrittenQuery, documentRepository.listAll(),
				documentTopK);
		List<EvidenceItem> selected = recallResult.items();
		log.debug("evidence 召回完成：threadId={}, selected={}", context.threadId(), selected.stream()
			.map(EvidenceItem::id)
			.limit(10)
			.toList());
		state.setEvidences(selected);
		state.setEvidenceText(knowledgeContextFormatter.formatEvidenceContext(selected));
		state.setDocumentText(knowledgeContextFormatter.formatDocumentContext(documentRecallResult.documents()));
		return new EvidenceRun(originalQuery, rewrittenQuery, selected, summarizeDocuments(documentRecallResult.documents()), state);
	}

	private static List<Map<String, Object>> summarizeDocuments(List<RecallDocument> documents) {
		if (documents == null || documents.isEmpty()) {
			return List.of();
		}
		return documents.stream().map(document -> Map.<String, Object>of("id", document.id(), "title", document.title(),
				"sectionTitle", String.valueOf(document.metadata().getOrDefault("sectionTitle", "")))).toList();
	}

	private record EvidenceRun(String originalQuery, String rewrittenQuery, List<EvidenceItem> selected,
			List<Map<String, Object>> documentSummaries, SearchLiteState state) {
		private int documentCount() {
			return documentSummaries == null ? 0 : documentSummaries.size();
		}
	}

}

