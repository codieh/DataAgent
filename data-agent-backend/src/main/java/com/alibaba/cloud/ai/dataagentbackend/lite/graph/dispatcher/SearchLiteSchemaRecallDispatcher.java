package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.ENHANCE_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.RESULT_NODE;

public class SearchLiteSchemaRecallDispatcher implements EdgeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteSchemaRecallDispatcher.class);

	@Override
	public String apply(OverAllState state) {
		List<String> recalledTables = state.value(SearchLiteGraphStateKeys.RECALLED_TABLES)
			.filter(List.class::isInstance)
			.map(List.class::cast)
			.map(list -> list.stream().filter(String.class::isInstance).map(String.class::cast).toList())
			.orElse(List.of());

		if (recalledTables.isEmpty()) {
			log.info("graph schema-recall dispatcher: no recalled tables, route to {}", RESULT_NODE);
			return RESULT_NODE;
		}

		log.info("graph schema-recall dispatcher: recalledTables={}, route to {}", recalledTables, ENHANCE_NODE);
		return ENHANCE_NODE;
	}

}
