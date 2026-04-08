package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PREPARE_RESULT_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.SQL_EXECUTE_NODE;

@Component
public class SearchLiteSqlGenerateDispatcher implements EdgeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteSqlGenerateDispatcher.class);

	@Override
	public String apply(OverAllState state) {
		String sql = state.value(SearchLiteGraphStateKeys.SQL)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.map(String::trim)
			.orElse("");

		if (isUsableSql(sql)) {
			log.info("graph sql-generate dispatcher: sqlLen={}, route to {}", sql.length(), SQL_EXECUTE_NODE);
			return SQL_EXECUTE_NODE;
		}

		log.info("graph sql-generate dispatcher: empty or invalid sql, route to {}", PREPARE_RESULT_NODE);
		return PREPARE_RESULT_NODE;
	}

	private static boolean isUsableSql(String sql) {
		if (sql == null || sql.isBlank()) {
			return false;
		}
		String normalized = sql.trim().toLowerCase();
		return normalized.startsWith("select") || normalized.startsWith("with");
	}

}
