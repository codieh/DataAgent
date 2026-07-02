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
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.Map;
import java.util.Objects;

/**
 * 语义一致性校验阶段：在 SQL 生成之后、执行之前，验证生成的 SQL 是否准确执行了指令，且所有表名/列名存在于 Schema 中。
 *
 * <p>
 * 如果校验不通过，会尝试使用 SQL 修复 prompt 重新生成 SQL（最多修复一次）。
 * </p>
 */
@Component
@Order(45)
public class SemanticConsistencyStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(SemanticConsistencyStep.class);

	private final SearchLiteLlmGateway llmGateway;

	private final ObjectMapper objectMapper;

	private final int maxRepairAttempts;

	private final boolean enabled;

	public SemanticConsistencyStep(SearchLiteLlmGateway llmGateway, ObjectMapper objectMapper,
			@Value("${search.lite.sql.consistency.max-repair:1}") int maxRepairAttempts,
			@Value("${search.lite.sql.consistency.enabled:false}") boolean enabled) {
		this.llmGateway = Objects.requireNonNull(llmGateway, "llmGateway");
		this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
		this.maxRepairAttempts = Math.max(0, maxRepairAttempts);
		this.enabled = enabled;
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.SQL_CONSISTENCY;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		if (!enabled) {
			Flux<SearchLiteMessage> msg = Flux.just(SearchLiteMessages.message(context, stage(),
					SearchLiteMessageType.TEXT, "已跳过语义一致性校验。", null));
			return new SearchLiteStepResult(msg, Mono.just(state));
		}
		String sql = state.getSql();
		if (!StringUtils.hasText(sql)) {
			Flux<SearchLiteMessage> msg = Flux.just(SearchLiteMessages.message(context, stage(),
					SearchLiteMessageType.TEXT, "SQL 为空，跳过语义校验。", null));
			return new SearchLiteStepResult(msg, Mono.just(state));
		}

		log.info("semantic-consistency start: threadId={}, sqlLen={}", context.threadId(), sql.length());

		Flux<SearchLiteMessage> start = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
					"正在进行语义一致性校验...", null))
			.delayElements(Duration.ofMillis(50));

		Mono<SearchLiteState> updated = validateAndRepair(context, state).cache();

		Flux<SearchLiteMessage> result = updated.map(s -> {
			if (StringUtils.hasText(s.getError())) {
				return SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
						"语义校验未通过：" + s.getError(), null);
			}
			return SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
					"语义一致性校验通过。", null);
		}).flux();

		return new SearchLiteStepResult(start.concatWith(result), updated);
	}

	private Mono<SearchLiteState> validateAndRepair(SearchLiteContext context, SearchLiteState state) {
		String sql = state.getSql();
		String instruction = state.getEffectiveQuery();
		String schema = resolveSchemaContext(state);
		String evidence = safeOrDefault(state.getEvidenceText(), "(无)");
		String userQuery = safe(state.getQuery());

		return callValidation(sql, instruction, schema, evidence, userQuery).map(validation -> {
			if (validation.startsWith("通过")) {
				log.info("semantic-consistency passed: threadId={}", context.threadId());
				state.setError(null);
				return new ValidationDecision(true, validation);
			}
			String reason = validation.startsWith("不通过") ? validation : "不通过。" + validation;
			log.info("semantic-consistency failed: threadId={}, reason={}", context.threadId(), reason);
			return new ValidationDecision(false, reason);
		}).flatMap(decision -> {
			if (decision.passed()) {
				return Mono.just(state);
			}
			if (maxRepairAttempts > 0 && state.getSqlRetryCount() < maxRepairAttempts) {
				return callRepair(sql, decision.reason(), instruction, schema, evidence, userQuery).map(repaired -> {
					if (StringUtils.hasText(repaired) && !repaired.equals(sql)) {
						log.info("semantic-consistency repaired: threadId={}, newSqlLen={}", context.threadId(),
								repaired.length());
						state.setSql(repaired);
						state.setLastFailedSql(sql);
						state.setSqlRetryReason(decision.reason());
						state.setSqlRetryCount(state.getSqlRetryCount() + 1);
						state.setError(null);
						return state;
					}
					return markRepairFallback(context, state);
				});
			}
			return Mono.just(markRepairFallback(context, state));
		});
	}

	private Mono<String> callValidation(String sql, String instruction, String schema, String evidence, String userQuery) {
		String system = """
				您是一位严格的 SQL 代码审计专家和 MySQL 语法专家。
				您的核心职责是验证生成的 SQL 是否准确执行了当前步骤的指令，并符合数据库规范。
				请严格只返回"通过"或"不通过。[具体原因]"。
				""".trim();

		String user = """
				# 审计上下文

				## 1. 当前执行指令 (核心依据)
				%s
				标准：SQL 必须且只需完成此指令要求的任务。

				## 2. 待验证 SQL
				%s

				## 3. 数据库 Schema (事实标准)
				%s

				## 4. 全局业务背景 (仅作参考)
				用户问题: %s
				业务参考信息: %s

				# 审计维度
				## 语义一致性：SQL 是否查询了指令中要求的表和字段？是否遗漏了明确要求的 WHERE 条件？
				## 结构正确性：SQL 中的所有表名和列名是否都能在 Schema 中找到？是否存在语法错误？

				# 判定标准
				## 不通过：查询了 Schema 中不存在的幻觉字段；逻辑与指令冲突；遗漏核心过滤条件；存在明显语法错误。
				## 通过：逻辑正确，字段存在；包含非核心的排序差异（允许）；包含多余的 ID 列（允许）。

				# 输出格式
				请严格只返回以下两种格式之一：
				1、通过
				2、不通过。[具体原因]
				""".formatted(safe(instruction), sql, safe(schema), safe(userQuery), evidence).trim();

		return llmGateway.completeAsync(system, user)
			.map(raw -> StringUtils.hasText(raw) ? raw.trim() : "通过")
			.onErrorResume(e -> {
				log.warn("semantic-consistency validation call failed: {}", e.getMessage());
				return Mono.just("通过");
			});
	}

	private Mono<String> callRepair(String sql, String reason, String instruction, String schema, String evidence,
			String userQuery) {
		String system = """
				你是一位精通 MySQL 的高级数据工程师和故障排查专家。
				你的任务是根据报错信息，修复一句存在问题的 SQL。
				仅输出修复后的 SQL 语句本身，不要输出任何额外标记。
				""".trim();

		String user = """
				# 故障现场

				## 1. 校验不通过原因
				%s

				## 2. 数据库 Schema (绝对标准)
				%s
				警告：修复后的字段必须严格存在于 Schema 中，严禁臆造字段。

				## 3. 当前执行任务 (修复目标)
				%s

				## 4. 原始 SQL
				%s

				## 5. 全局业务背景 (参考)
				用户问题: %s
				业务参考信息: %s

				# 修复策略
				- Schema 对齐：如果提示字段不存在，在 Schema 中寻找最接近的正确列名。
				- 最小化修改：只修复错误，不要过度优化或重写原本正确的逻辑。
				- 安全转义：对所有表名和列名使用反引号转义。

				# 输出格式
				仅输出修复后的 SQL 语句，不要使用任何额外标记，特别是 Markdown 标记。

				---

				# 示例输出

				❌ 错误输出（带有 Markdown 标记）：
				```sql
				select `id`, `name` from `user`;
				```

				✅ 正确输出（纯 SQL 语句）：
				select `id`, `name` from `user` limit 200;

				---
				""".formatted(safe(reason), safe(schema), safe(instruction), sql, safe(userQuery), evidence).trim();

		return llmGateway.completeAsync(system, user).map(this::parseSql).onErrorResume(e -> {
			log.warn("semantic-consistency repair call failed: {}", e.getMessage());
			return Mono.justOrEmpty((String) null);
		});
	}

	private SearchLiteState markRepairFallback(SearchLiteContext context, SearchLiteState state) {
		log.warn("semantic-consistency repair failed, proceeding with original SQL: threadId={}", context.threadId());
		state.setError(null);
		return state;
	}

	private String parseSql(String raw) {
		if (!StringUtils.hasText(raw)) {
			return "";
		}
		String trimmed = raw.trim();
		// 去掉 ```sql ... ``` 代码围栏
		String withoutFences = trimmed.replace("```sql", "").replace("```SQL", "").replace("```", "").trim();
		// 只取第一条语句
		int semi = withoutFences.indexOf(';');
		if (semi > 0) {
			withoutFences = withoutFences.substring(0, semi).trim();
		}
		return withoutFences;
	}

	private static String resolveSchemaContext(SearchLiteState state) {
		String recalled = state == null ? "" : state.getRecalledSchemaText();
		String full = state == null ? "" : state.getSchemaText();
		return StringUtils.hasText(recalled) ? recalled : safe(full);
	}

	private static String safe(String s) {
		return s == null ? "" : s.trim();
	}

	private static String safeOrDefault(String value, String fallback) {
		return StringUtils.hasText(value) ? value.trim() : fallback;
	}

	private record ValidationDecision(boolean passed, String reason) {
	}

}
