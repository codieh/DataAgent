package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.util.List;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLAN_EXECUTOR_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.SQL_RETRY_NODE;

@Component
public class SearchLiteSqlRepairDispatcher implements EdgeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteSqlRepairDispatcher.class);

	private final int maxRetryAttempts;

	public SearchLiteSqlRepairDispatcher(@Value("${search.lite.graph.sql-retry.max-attempts:1}") int maxRetryAttempts) {
		this.maxRetryAttempts = Math.max(0, maxRetryAttempts);
	}

	@Override
	public String apply(OverAllState state) {
		String error = state.value(SearchLiteGraphStateKeys.ERROR)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.map(String::trim)
			.orElse("");
		int retryCount = state.value(SearchLiteGraphStateKeys.SQL_RETRY_COUNT)
			.filter(Integer.class::isInstance)
			.map(Integer.class::cast)
			.orElse(0);
		String sql = state.value(SearchLiteGraphStateKeys.SQL)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.orElse("");

		if (error.isBlank()) {
			// Repair succeeded
			log.info("graph sql-repair dispatcher: repair succeeded, route to {}", PLAN_EXECUTOR_NODE);
			return PLAN_EXECUTOR_NODE;
		}

		// Repair failed, try retry loop if allowed
		if (retryCount < maxRetryAttempts && !sql.isBlank() && isRetryableError(error)) {
			log.info("graph sql-repair dispatcher: repair failed, retryCount={}, route to {}", retryCount, SQL_RETRY_NODE);
			return SQL_RETRY_NODE;
		}

		log.info("graph sql-repair dispatcher: repair failed, retry exhausted, route to {}", PLAN_EXECUTOR_NODE);
		return PLAN_EXECUTOR_NODE;
	}

	private boolean isRetryableError(String error) {
		String normalized = error == null ? "" : error.toLowerCase();
		if (normalized.isBlank()) {
			return false;
		}
		return !(normalized.contains("communications link failure") || normalized.contains("connection refused")
				|| normalized.contains("access denied") || normalized.contains("connect timed out")
				|| normalized.contains("read timed out"));
	}

}
