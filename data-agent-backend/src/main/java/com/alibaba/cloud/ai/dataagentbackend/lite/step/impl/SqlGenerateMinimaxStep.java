package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.alibaba.cloud.ai.dataagentbackend.llm.anthropic.AnthropicClient;
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

	private final AnthropicClient anthropicClient;

	private final ObjectMapper objectMapper;

	private final int defaultLimit;

	public SqlGenerateMinimaxStep(AnthropicClient anthropicClient, ObjectMapper objectMapper,
			@Value("${search.lite.sql.generate.limit:200}") int defaultLimit) {
		this.anthropicClient = Objects.requireNonNull(anthropicClient, "anthropicClient");
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

		int schemaLen = schema == null ? 0 : schema.length();
		int evidenceLen = evidence == null ? 0 : evidence.length();
		int documentLen = documents == null ? 0 : documents.length();
		log.info("sql-generate start: threadId={}, qLen={}, schemaLen={}, evidenceLen={}, documentLen={}", context.threadId(),
				question == null ? 0 : question.length(), schemaLen, evidenceLen, documentLen);

		String system = """
				You are a senior data analyst who writes correct and safe SQL.
				Return ONLY a single MySQL SELECT statement.
				Do NOT return markdown, code fences, explanations, or JSON.
				""".trim();

		String user = buildSqlGenerationPrompt(question, schema, evidence, documents, defaultLimit);

		Flux<SearchLiteMessage> start = Flux.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
				"正在生成 SQL...", null)).delayElements(Duration.ofMillis(50));

		Flux<String> sharedDeltas = anthropicClient.streamMessage(system, user).cache();

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

	static String buildSqlGenerationPrompt(String question, String schema, String evidence, String documents,
			int defaultLimit) {
		return """
				User question:
				%s

				Authoritative database schema (STRUCTURE SOURCE, must be obeyed):
				%s

				Supporting business rules and FAQ hints:
				%s

				Supporting definitions and background documents:
				%s

				How to use context:
				- Treat schema as the hard constraint for tables, columns, joins, and SQL structure.
				- Use ONLY tables/columns that exist in the schema section.
				- Treat evidence as explicit business rules, FAQ answers, or metric calculation hints.
				- Treat documents as concept definitions and background explanations, especially for business terms like user segments and metrics.
				- If evidence conflicts with schema, always trust schema.
				- If documents conflict with schema, always trust schema.
				- If a document provides a definition that clearly matches the user question, prefer that definition over unrelated evidence.
				- If evidence or documents are irrelevant to the current question, ignore them.

				Constraints:
				- Output must be a single MySQL SELECT statement (no semicolons, no multiple statements).
				- Prefer clear table aliases.
				- Always add LIMIT %d unless the question explicitly asks for all rows.
				- Do NOT add debug/system columns (e.g., CURRENT_USER(), USER(), VERSION(), @@variables).
				- Avoid reserved keywords as aliases.
				- If the question is ambiguous or cannot be answered with the schema, still output the best-effort SELECT.
				""".formatted(safe(question), safe(schema), safe(evidence), safe(documents), Math.max(1, defaultLimit)).trim();
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

	private static String safe(String s) {
		return s == null ? "" : s.trim();
	}

}
