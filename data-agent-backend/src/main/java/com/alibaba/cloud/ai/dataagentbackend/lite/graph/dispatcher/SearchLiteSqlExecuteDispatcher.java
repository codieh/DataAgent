package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.List;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PREPARE_RESULT_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.SQL_RETRY_NODE;

@Component
public class SearchLiteSqlExecuteDispatcher implements EdgeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteSqlExecuteDispatcher.class);

	private final int maxRetryAttempts;

	public SearchLiteSqlExecuteDispatcher(@Value("${search.lite.graph.sql-retry.max-attempts:1}") int maxRetryAttempts) {
		this.maxRetryAttempts = Math.max(0, maxRetryAttempts);
	}

	@Override
	public String apply(OverAllState state) {
		String error = state.value(SearchLiteGraphStateKeys.ERROR)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.map(String::trim)
			.orElse("");
		int rowCount = state.value(SearchLiteGraphStateKeys.ROWS)
			.filter(List.class::isInstance)
			.map(List.class::cast)
			.map(List::size)
			.orElse(0);
		int retryCount = state.value(SearchLiteGraphStateKeys.SQL_RETRY_COUNT)
			.filter(Integer.class::isInstance)
			.map(Integer.class::cast)
			.orElse(0);
		String sql = state.value(SearchLiteGraphStateKeys.SQL)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.orElse("");
		String resultMode = state.value(SearchLiteGraphStateKeys.RESULT_MODE)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.orElse("");

		if (!error.isBlank()) {
			if (resultMode.startsWith("blocked_")) {
				log.info("graph sql-execute dispatcher: policy blocked, route to {}, mode={}", PREPARE_RESULT_NODE,
						resultMode);
				return PREPARE_RESULT_NODE;
			}
			if (shouldRetry(error, sql, retryCount)) {
				log.info("graph sql-execute dispatcher: execution failed, retryCount={}, route to {}, error={}", retryCount,
						SQL_RETRY_NODE, error);
				return SQL_RETRY_NODE;
			}
			log.info("graph sql-execute dispatcher: execution failed, retry exhausted or not retryable, route to {}, error={}",
					PREPARE_RESULT_NODE, error);
			return PREPARE_RESULT_NODE;
		}

		log.info("graph sql-execute dispatcher: execution ok, rows={}, route to {}", rowCount, PREPARE_RESULT_NODE);
		return PREPARE_RESULT_NODE;
	}

	private boolean shouldRetry(String error, String sql, int retryCount) {
		if (retryCount >= maxRetryAttempts || sql == null || sql.isBlank()) {
			return false;
		}
		String normalized = error == null ? "" : error.toLowerCase();
		if (normalized.isBlank()) {
			return false;
		}
		return !(normalized.contains("communications link failure") || normalized.contains("connection refused")
				|| normalized.contains("access denied") || normalized.contains("connect timed out")
				|| normalized.contains("read timed out"));
	}

}
