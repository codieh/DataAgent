package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallService;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.SchemaRecallResult;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * 从已抽取的 schema 中，选择本次请求最相关的少量数据表（TopK）。
 *
 * <p>
 * 目的：
 * <ul>
 *   <li>避免把全量 schema 都喂给模型（噪声大、token 多）。</li>
 *   <li>为后续 SQL 生成提供更聚焦的 {@code recalledSchemaText}。</li>
 * </ul>
 * </p>
 *
 * <p>
 * 当前策略：基于 query + evidenceText 的粗糙关键词匹配打分。
 * 后续可替换为向量检索（更接近 management 的做法）。
 * </p>
 */
@Component
@Order(32)
public class SchemaRecallStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(SchemaRecallStep.class);

	private final RecallService recallService;

	private final int topK;

	public SchemaRecallStep(RecallService recallService, @Value("${search.lite.schema.recall.top-k:3}") int topK) {
		this.recallService = recallService;
		this.topK = Math.max(1, topK);
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.SCHEMA_RECALL;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		Flux<SearchLiteMessage> start = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在选择相关数据表（schema recall）...", null))
			.delayElements(Duration.ofMillis(40));

		List<SchemaTable> tables = state.getSchemaTableDetails();
		if (tables == null || tables.isEmpty()) {
			Flux<SearchLiteMessage> msg = Flux.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
					"未发现可用 schema，请先初始化/抽取 schema。", null));
			return new SearchLiteStepResult(start.concatWith(msg), Mono.just(state));
		}

		SchemaRecallResult recallResult = recallService.recallSchema(state.getQuery(), state.getEvidenceText(), tables, topK);
		List<SchemaTable> recalled = recallResult.tables();
		List<String> recalledNames = recallResult.tableNames();
		String recalledSchemaText = recallResult.promptText();

		log.info("schema recall：threadId={}, recalledTables={}", context.threadId(), recalledNames);
		state.setRecalledTables(recalledNames);
		state.setRecalledSchemaText(recalledSchemaText);

		Flux<SearchLiteMessage> tableMsg = Flux.just(SearchLiteMessages.message(context, stage(),
				SearchLiteMessageType.TEXT, "已选择表: " + String.join(", ", recalledNames), null));

		Flux<SearchLiteMessage> payload = Flux.just(SearchLiteMessages.message(context, stage(),
				SearchLiteMessageType.JSON, null, Map.of("recalledTables", recalledNames, "recalledSchemaTextLen",
						recalledSchemaText.length(), "tableHitCount", recallResult.tableHits().size(), "columnHitCount",
						recallResult.columnHits().size())));

		return new SearchLiteStepResult(start.concatWith(tableMsg).concatWith(payload), Mono.just(state));
	}

}
