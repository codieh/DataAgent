package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.RESULT_NODE;

public class SearchLiteSqlExecuteDispatcher implements EdgeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteSqlExecuteDispatcher.class);

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

		if (!error.isBlank()) {
			log.info("graph sql-execute dispatcher: execution failed, route to {}, error={}", RESULT_NODE, error);
			return RESULT_NODE;
		}

		log.info("graph sql-execute dispatcher: execution ok, rows={}, route to {}", rowCount, RESULT_NODE);
		return RESULT_NODE;
	}

}
