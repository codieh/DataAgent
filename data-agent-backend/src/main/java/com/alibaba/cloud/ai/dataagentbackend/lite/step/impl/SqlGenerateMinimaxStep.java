package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.llm.SearchLiteLlmGateway;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.Map;
import java.util.Objects;

/**
 * SQL 生成阶段：使用 MiniMax（Anthropic 兼容接口）把自然语言问题转为可执行的 MySQL SELECT 语句。
 *
 * <p>
 * 设计目标：
 * <ul>
 *   <li>真流式：把模型输出 delta 以 SSE 方式实时推送给前端；</li>
 *   <li>可控上下文：优先使用 {@code recalledSchemaText}（相关表）而不是全量 schema；</li>
 *   <li>最小约束：要求模型只输出 SQL（无 markdown），并建议加 LIMIT。</li>
 * </ul>
 * </p>
 */
@Component
@Order(40)
@ConditionalOnProperty(name = "search.lite.sql.generate.provider", havingValue = "minimax", matchIfMissing = true)
public class SqlGenerateMinimaxStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(SqlGenerateMinimaxStep.class);

	private final SearchLiteLlmGateway llmGateway;

	private final ObjectMapper objectMapper;

	private final int defaultLimit;

	public SqlGenerateMinimaxStep(SearchLiteLlmGateway llmGateway, ObjectMapper objectMapper,
			@Value("${search.lite.sql.generate.limit:200}") int defaultLimit) {
		this.llmGateway = Objects.requireNonNull(llmGateway, "llmGateway");
		this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
		this.defaultLimit = Math.max(1, defaultLimit);
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.SQL_GENERATE;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		if (!"DATA_ANALYSIS".equalsIgnoreCase(safe(state.getIntentClassification()))) {
			Flux<SearchLiteMessage> msg = Flux.just(SearchLiteMessages.message(context, stage(),
					SearchLiteMessageType.TEXT, "当前意图不是数据分析，跳过 SQL 生成。", null));
			return new SearchLiteStepResult(msg, Mono.just(state));
		}

		String question = state.getEffectiveQuery();
		String schema = resolveSchemaContext(state);
		String evidence = resolveEvidenceContext(state);
		String documents = resolveDocumentContext(state);
		String retryHint = resolveRetryHint(state);
		String planContext = resolvePlanContext(state);

		int schemaLen = schema == null ? 0 : schema.length();
		int evidenceLen = evidence == null ? 0 : evidence.length();
		int documentLen = documents == null ? 0 : documents.length();
		log.info("sql-generate start: threadId={}, qLen={}, schemaLen={}, evidenceLen={}, documentLen={}", context.threadId(),
				question == null ? 0 : question.length(), schemaLen, evidenceLen, documentLen);

		String system = """
				你是一位精通 MySQL 的高级数据工程师。
				你的任务是根据【数据库 Schema】和用户问题，编写一句高效、准确的 SQL 查询语句。
				仅输出 SQL 语句本身，不要输出任何额外标记，特别是 Markdown 标记。
				""".trim();

		String user = buildSqlGenerationPrompt(question, schema, evidence, documents, retryHint, planContext, defaultLimit);

		Flux<SearchLiteMessage> start = Flux.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
				"正在生成 SQL...", null)).delayElements(Duration.ofMillis(50));

		Flux<String> sharedDeltas = llmGateway.streamAsync(system, user).cache();

		Flux<SearchLiteMessage> streaming = sharedDeltas
			.map(delta -> SearchLiteMessages.message(context, stage(), SearchLiteMessageType.SQL, delta, null));

		Mono<SearchLiteState> updated = sharedDeltas.collect(StringBuilder::new, StringBuilder::append).map(sb -> {
			String raw = sb.toString();
			String sql = parseSql(raw);
			state.setSql(sql);
			return state;
		});

		Flux<SearchLiteMessage> done = updated.map(s -> SearchLiteMessages.message(context, stage(),
				SearchLiteMessageType.SQL, null, Map.of("sql", s.getSql(), "sqlLen", s.getSql() == null ? 0 : s.getSql().length()))).flux();

		return new SearchLiteStepResult(start.concatWith(streaming).concatWith(done), updated);
	}

	private String parseSql(String raw) {
		if (!StringUtils.hasText(raw)) {
			return "";
		}
		String trimmed = raw.trim();

		// 兼容模型偶尔输出 JSON 的情况
		if (trimmed.startsWith("{") && trimmed.contains("\"sql\"")) {
			try {
				@SuppressWarnings("unchecked")
				Map<String, Object> map = objectMapper.readValue(trimmed, Map.class);
				Object sql = map.get("sql");
				if (sql instanceof String s) {
					trimmed = s.trim();
				}
			}
			catch (Exception ignored) {
				// fall through
			}
		}

		// 去掉 ```sql ... ``` 代码围栏
		String withoutFences = trimmed.replace("```sql", "").replace("```SQL", "").replace("```", "").trim();

		// 只取第一条语句（如果不小心带了分号）
		int semi = withoutFences.indexOf(';');
		if (semi > 0) {
			withoutFences = withoutFences.substring(0, semi).trim();
		}
		return withoutFences;
	}

	static String buildSqlGenerationPrompt(String question, String schema, String evidence, String documents, String retryHint,
			String planContext, int defaultLimit) {
		return """
				# 用户问题
				%s

				# 数据库 Schema（绝对事实，必须严格遵循）
				%s
				注意：你编写的 SQL 中所有表名和列名必须严格存在于上述 Schema 中，严禁臆造不存在的字段。

				# 业务知识（参考）
				%s

				# 文档定义（参考）
				%s

				# 重试提示
				%s

				# 计划上下文
				%s

				# 上下文使用规则
				- Schema 是硬约束：SQL 的表名、列名、JOIN 路径必须严格来自 Schema。
				- 业务知识是参考：如果业务知识与 Schema 冲突，以 Schema 为准。
				- 文档定义是参考：用于理解业务术语的含义，但不能引入 Schema 中不存在的表或列。
				- 如果重试提示存在，修复上次 SQL 的错误，但保持业务意图不变。
				- 如果计划上下文存在，仅在当前步骤依赖前序结果时使用。

				# SQL 编写约束
				1. 输出必须是单条 MySQL SELECT 语句（无分号，无多条语句）。
				2. 使用清晰的表别名。
				3. 禁止使用 SELECT *，只选择需要的列。
				4. 问题未明确要求明细时，优先输出聚合/统计结果。
				5. 除非问题明确要求所有行，否则必须添加 LIMIT %d。
				6. 禁止使用系统函数（CURRENT_USER(), USER(), VERSION(), @@variables）。
				7. 禁止直接查询敏感字段（phone, mobile, email, id_card, salary, wage, bank_card, address），除非问题明确要求且策略允许。
				8. 避免使用 MySQL 保留字作为别名。
				9. 如果问题模糊或 Schema 无法完全回答，仍然输出最佳努力的 SELECT。

				# 输出格式
				仅输出 SQL 语句，不要使用任何额外标记，特别是 Markdown 标记。

				---

				# 输出示例

				❌ 错误输出（带有 Markdown 标记，会导致执行器解析失败）：
				```sql
				select `id`, `name` from `user`;
				```

				✅ 正确输出（纯 SQL 语句）：
				select `id`, `name` from `user` limit 200;

				---
				""".formatted(safe(question), safe(schema), safe(evidence), safe(documents), safe(retryHint), safe(planContext),
					Math.max(1, defaultLimit)).trim();
	}

	private static String resolveSchemaContext(SearchLiteState state) {
		String recalled = state == null ? "" : state.getRecalledSchemaText();
		String full = state == null ? "" : state.getSchemaText();
		return StringUtils.hasText(recalled) ? recalled : safe(full);
	}

	private static String resolveEvidenceContext(SearchLiteState state) {
		if (state == null) {
			return "(无 evidence)";
		}
		String evidence = safe(state.getEvidenceText());
		if (!StringUtils.hasText(evidence)) {
			return "(无 evidence)";
		}
		return evidence;
	}

	private static String resolveDocumentContext(SearchLiteState state) {
		if (state == null) {
			return "(无文档定义补充)";
		}
		String documents = safe(state.getDocumentText());
		if (!StringUtils.hasText(documents)) {
			return "(无文档定义补充)";
		}
		return documents;
	}

	private static String resolveRetryHint(SearchLiteState state) {
		if (state == null || state.getSqlRetryCount() <= 0) {
			return "(无)";
		}
		String failedSql = safe(state.getLastFailedSql());
		String reason = safe(state.getSqlRetryReason());
		return """
				Retry count: %d
				Previous failed SQL:
				%s

				Execution error:
				%s
				""".formatted(state.getSqlRetryCount(), failedSql, reason).trim();
	}

	private static String resolvePlanContext(SearchLiteState state) {
		if (state == null || state.getPlanSteps() == null || state.getPlanSteps().isEmpty()) {
			return "(无多步骤计划)";
		}
		StringBuilder builder = new StringBuilder();
		builder.append("Current step index: ").append(state.getCurrentPlanStepIndex() + 1).append('\n');
		builder.append("Use previous completed steps only as structured constraints for the current step.\n");
		for (var step : state.getPlanSteps()) {
			if (step == null) {
				continue;
			}
			builder.append("- Step ").append(step.getStep()).append('\n');
			builder.append("  Instruction: ").append(safe(step.getInstruction())).append('\n');
			builder.append("  Status: ").append(safe(step.getStatus())).append('\n');
			if (StringUtils.hasText(step.getSql())) {
				builder.append("  SQL: ").append(step.getSql()).append('\n');
			}
			builder.append("  Row count: ").append(step.getRowCount()).append('\n');
			builder.append("  Preview rows: ").append(step.getPreviewRows() == null ? "[]" : step.getPreviewRows()).append('\n');
			if (StringUtils.hasText(step.getSummarySnippet())) {
				builder.append("  Summary: ").append(step.getSummarySnippet()).append('\n');
			}
			if (StringUtils.hasText(step.getError())) {
				builder.append("  Error: ").append(step.getError()).append('\n');
			}
		}
		return builder.toString().trim();
	}

	private static String safe(String s) {
		return s == null ? "" : s.trim();
	}

}
