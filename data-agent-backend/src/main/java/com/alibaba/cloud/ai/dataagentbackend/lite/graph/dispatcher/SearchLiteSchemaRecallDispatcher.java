package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.List;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.ENHANCE_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PREPARE_RESULT_NODE;

@Component
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
			log.info("graph schema-recall dispatcher: no recalled tables, route to {}", PREPARE_RESULT_NODE);
			return PREPARE_RESULT_NODE;
		}

		log.info("graph schema-recall dispatcher: recalledTables={}, route to {}", recalledTables, ENHANCE_NODE);
		return ENHANCE_NODE;
	}

}
