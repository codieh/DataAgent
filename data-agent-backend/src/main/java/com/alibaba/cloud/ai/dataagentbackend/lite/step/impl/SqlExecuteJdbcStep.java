package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
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
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * SQL 执行阶段：使用 JDBC 真实执行（精简版）。
 *
 * <p>
 * 注意：JDBC 是阻塞式调用，必须切到 {@code boundedElastic}，避免阻塞 WebFlux 线程。
 * </p>
 */
@Component
@Order(50)
@ConditionalOnProperty(name = "search.lite.sql.execute.provider", havingValue = "jdbc")
public class SqlExecuteJdbcStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(SqlExecuteJdbcStep.class);

	private final JdbcTemplate jdbcTemplate;

	private final int limit;

	private final int queryTimeoutSeconds;

	public SqlExecuteJdbcStep(JdbcTemplate jdbcTemplate, @Value("${search.lite.sql.execute.limit:200}") int limit,
			@Value("${search.lite.sql.execute.timeout-seconds:5}") int queryTimeoutSeconds) {
		this.jdbcTemplate = Objects.requireNonNull(jdbcTemplate, "jdbcTemplate");
		this.limit = Math.max(1, limit);
		this.queryTimeoutSeconds = Math.max(1, queryTimeoutSeconds);
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.SQL_EXECUTE;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		String sql = state.getSql();
		if (!StringUtils.hasText(sql)) {
			Flux<SearchLiteMessage> msg = Flux.just(SearchLiteMessages.message(context, stage(),
					SearchLiteMessageType.TEXT, "SQL 为空，跳过执行。", null));
			return new SearchLiteStepResult(msg, Mono.just(state));
		}

		Flux<SearchLiteMessage> start = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在执行 SQL...", null))
			.delayElements(Duration.ofMillis(50));

		Mono<ExecOutcome> exec = Mono.fromCallable(() -> {
			try {
				ExecutionResult r = execute(sql);
				return ExecOutcome.ok(r.sql, r.columns, r.rows);
			}
			catch (Exception e) {
				String msg = e.getMessage() == null ? "SQL 执行失败" : e.getMessage();
				return ExecOutcome.fail(sql, msg);
			}
		})
			.subscribeOn(Schedulers.boundedElastic())
			.doOnSubscribe(s -> log.info("sql-execute start: threadId={}, timeout={}s", context.threadId(),
					queryTimeoutSeconds))
			.doOnSuccess(r -> log.info("sql-execute done: threadId={}, ok={}, rows={}", context.threadId(),
					r != null && r.ok, r == null || r.rows == null ? 0 : r.rows.size()))
			.cache();

		Flux<SearchLiteMessage> sqlMsg = exec.map(r -> SearchLiteMessages.message(context, stage(),
				SearchLiteMessageType.SQL, r.sql, Map.of("sql", r.sql, "guarded", true, "ok", r.ok))).flux();

		Flux<SearchLiteMessage> resultSet = exec.flatMapMany(r -> {
			if (r.ok) {
				return Flux.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.RESULT_SET, null,
						Map.of("columns", r.columns, "rows", r.rows)));
			}
			return Flux.just(SearchLiteMessages.error(context, stage(), r.error));
		});

		Mono<SearchLiteState> updated = exec.map(r -> {
			state.setSql(r.sql);
			state.setRows(r.rows == null ? List.of() : r.rows);
			if (!r.ok) {
				state.setLastFailedSql(r.sql);
				state.setSqlRetryReason(r.error);
				state.setError(r.error);
			}
			else {
				state.setError(null);
				state.setSqlRetryReason(null);
			}
			return state;
		});

		return new SearchLiteStepResult(start.concatWith(sqlMsg).concatWith(resultSet), updated);
	}

	private ExecutionResult execute(String rawSql) {
		// 1) guardrails（精简版）
		SqlGuards.validateSelectOnly(rawSql);
		String guardedSql = SqlGuards.ensureLimit(rawSql, limit);

		// 2) 超时（JdbcTemplate 级别设置，作用于本次线程内执行的 statement）
		Integer oldTimeout = jdbcTemplate.getQueryTimeout();
		jdbcTemplate.setQueryTimeout(queryTimeoutSeconds);
		try {
			List<Map<String, Object>> rows = jdbcTemplate.queryForList(guardedSql);
			List<Map<String, Object>> safeRows = rows == null ? List.of() : rows;
			List<String> columns = extractColumns(safeRows);
			return new ExecutionResult(guardedSql, columns, safeRows);
		}
		finally {
			// 恢复默认值，避免影响其他请求
			jdbcTemplate.setQueryTimeout(oldTimeout == null ? 0 : oldTimeout);
		}
	}

	private static List<String> extractColumns(List<Map<String, Object>> rows) {
		if (rows == null || rows.isEmpty()) {
			return List.of();
		}
		Set<String> cols = new LinkedHashSet<>();
		for (Map<String, Object> row : rows) {
			if (row != null) {
				cols.addAll(row.keySet());
			}
		}
		return new ArrayList<>(cols);
	}

	private record ExecutionResult(String sql, List<String> columns, List<Map<String, Object>> rows) {
	}

	private record ExecOutcome(boolean ok, String sql, List<String> columns, List<Map<String, Object>> rows,
			String error) {
		static ExecOutcome ok(String sql, List<String> columns, List<Map<String, Object>> rows) {
			return new ExecOutcome(true, sql, columns == null ? List.of() : columns, rows == null ? List.of() : rows,
					null);
		}

		static ExecOutcome fail(String sql, String error) {
			return new ExecOutcome(false, sql, List.of(), List.of(), error);
		}
	}

}
