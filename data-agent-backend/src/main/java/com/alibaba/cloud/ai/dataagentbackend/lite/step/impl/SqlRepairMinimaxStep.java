package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.llm.SearchLiteLlmGateway;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.sql.SqlGuards;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * SQL 修复阶段：当 SQL 执行失败时，使用独立的修复 prompt 尝试自动修复并重新执行。
 *
 * <p>
 * 设计目标：
 * <ul>
 *   <li>将 SQL 修复逻辑从 SQL 生成 prompt 中分离，使用专门的修复 prompt（参考 management 的 sql-error-fixer.txt）；</li>
 *   <li>在 pipeline 模式下提供一次自动修复机会，无需依赖 graph 模式的重试循环；</li>
 *   <li>修复成功后自动重新执行，更新结果。</li>
 * </ul>
 * </p>
 */
@Component
@Order(55)
@ConditionalOnProperty(name = "search.lite.sql.repair.provider", havingValue = "minimax", matchIfMissing = true)
public class SqlRepairMinimaxStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(SqlRepairMinimaxStep.class);

	private final SearchLiteLlmGateway llmGateway;

	private final JdbcTemplate jdbcTemplate;

	private final int limit;

	private final int queryTimeoutSeconds;

	public SqlRepairMinimaxStep(SearchLiteLlmGateway llmGateway, JdbcTemplate jdbcTemplate,
			@Value("${search.lite.sql.execute.limit:200}") int limit,
			@Value("${search.lite.sql.execute.timeout-seconds:5}") int queryTimeoutSeconds) {
		this.llmGateway = Objects.requireNonNull(llmGateway, "llmGateway");
		this.jdbcTemplate = Objects.requireNonNull(jdbcTemplate, "jdbcTemplate");
		this.limit = Math.max(1, limit);
		this.queryTimeoutSeconds = Math.max(1, queryTimeoutSeconds);
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.SQL_REPAIR;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		// 仅在执行失败且有失败 SQL 时尝试修复
		if (!StringUtils.hasText(state.getError()) || !StringUtils.hasText(state.getLastFailedSql())) {
			Flux<SearchLiteMessage> msg = Flux.just(SearchLiteMessages.message(context, stage(),
					SearchLiteMessageType.TEXT, "SQL 执行成功，无需修复。", null));
			return new SearchLiteStepResult(msg, Mono.just(state));
		}

		// 已经重试过，不再修复
		if (state.getSqlRetryCount() > 0) {
			Flux<SearchLiteMessage> msg = Flux.just(SearchLiteMessages.message(context, stage(),
					SearchLiteMessageType.TEXT, "已尝试过修复，跳过。", null));
			return new SearchLiteStepResult(msg, Mono.just(state));
		}

		String failedSql = state.getLastFailedSql();
		String errorReason = state.getSqlRetryReason();

		log.info("sql-repair start: threadId={}, failedSqlLen={}, error={}", context.threadId(),
				failedSql.length(), errorReason);

		Flux<SearchLiteMessage> start = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
					"SQL 执行失败，正在尝试自动修复...", null))
			.delayElements(Duration.ofMillis(50));

		Mono<SearchLiteState> updated = callRepair(failedSql, errorReason, state).flatMap(repairedSql -> {
			if (!StringUtils.hasText(repairedSql) || repairedSql.equals(failedSql)) {
				log.info("sql-repair no change: threadId={}", context.threadId());
				state.setSqlRetryCount(1);
				return Mono.just(state);
			}

			log.info("sql-repair attempting re-execute: threadId={}, newSqlLen={}", context.threadId(), repairedSql.length());
			state.setSql(repairedSql);
			state.setSqlRetryCount(1);
			return Mono.fromCallable(() -> reExecute(context, state, repairedSql))
				.subscribeOn(Schedulers.boundedElastic());
		}).cache();

		Flux<SearchLiteMessage> result = updated.map(s -> {
			if (StringUtils.hasText(s.getError())) {
				return SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
						"自动修复未能解决问题，将使用原始错误信息。", null);
			}
			return SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
					"SQL 自动修复成功并重新执行。", null);
		}).flux();

		return new SearchLiteStepResult(start.concatWith(result), updated);
	}

	private Mono<String> callRepair(String failedSql, String errorReason, SearchLiteState state) {
		String schema = resolveSchemaContext(state);
		String instruction = state.getEffectiveQuery();
		String userQuery = safe(state.getQuery());
		String evidence = safeOrDefault(state.getEvidenceText(), "(无)");

		String system = """
				你是一位精通 MySQL 的高级数据工程师和故障排查专家。
				你的任务是根据报错信息，修复一句执行失败的 SQL。
				仅输出修复后的 SQL 语句本身，不要输出任何额外标记。
				""".trim();

		String user = """
				# 故障现场

				## 1. 报错信息 (关键)
				%s
				请仔细阅读上述报错，定位是语法错误、列名错误还是函数不兼容。

				## 2. 数据库 Schema (绝对标准)
				%s
				警告：修复后的字段必须严格存在于 Schema 中，严禁臆造字段。

				## 3. 当前执行任务 (修复目标)
				%s
				你的修复必须确保 SQL 仍然在执行这个任务，不要偏离目标。

				## 4. 原始失败 SQL
				%s

				## 5. 全局业务背景 (参考)
				用户问题: %s
				业务参考信息: %s

				# 修复策略
				- 方言纠正：严格检查是否使用了不符合 MySQL 的函数或语法。
				- Schema 对齐：如果报错提示"Column not found"，在 Schema 中寻找最接近的正确列名。
				- 最小化修改：只修复错误，不要过度优化或重写原本正确的逻辑。
				- 安全转义：对所有表名和列名使用反引号转义，避免保留字冲突。

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

				# 最终指令确认
				不管全局任务背景多么复杂，你的修复的 SQL 唯一目标是仅完成以下任务：
				%s
				""".formatted(safe(errorReason), safe(schema), safe(instruction), failedSql, userQuery, evidence,
					safe(instruction)).trim();

		return llmGateway.completeAsync(system, user).map(this::parseSql).onErrorResume(e -> {
			log.warn("sql-repair llm call failed: {}", e.getMessage());
			return Mono.empty();
		});
	}

	private SearchLiteState reExecute(SearchLiteContext context, SearchLiteState state, String repairedSql) {
		try {
			String guardedSql = SqlGuards.ensureLimit(repairedSql, limit);
			Integer oldTimeout = jdbcTemplate.getQueryTimeout();
			jdbcTemplate.setQueryTimeout(queryTimeoutSeconds);
			try {
				List<Map<String, Object>> rows = jdbcTemplate.queryForList(guardedSql);
				List<Map<String, Object>> safeRows = rows == null ? List.of() : rows;
				state.setSql(guardedSql);
				state.setRows(safeRows);
				state.setError(null);
				state.setSqlRetryReason(null);
				state.setResultMode(null);
				log.info("sql-repair re-execute succeeded: threadId={}, rows={}", context.threadId(), safeRows.size());
			}
			finally {
				jdbcTemplate.setQueryTimeout(oldTimeout == null ? 0 : oldTimeout);
			}
		}
		catch (Exception reExecEx) {
			String reExecMsg = reExecEx.getMessage() == null ? "修复后 SQL 仍然执行失败" : reExecEx.getMessage();
			log.info("sql-repair re-execute failed: threadId={}, error={}", context.threadId(), reExecMsg);
		}
		return state;
	}

	private String parseSql(String raw) {
		if (!StringUtils.hasText(raw)) {
			return "";
		}
		String trimmed = raw.trim();
		// 去掉代码围栏
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

}
