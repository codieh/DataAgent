package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class SearchLiteContinueGraphNode implements NodeAction {

	public static final String ROUTE_CONTINUE_PIPELINE = "continuePipeline";

	private static final Logger log = LoggerFactory.getLogger(SearchLiteContinueGraphNode.class);

	@Override
	public Map<String, Object> apply(OverAllState state) {
		log.debug("search-lite graph continue node invoked");
		return Map.of(SearchLiteGraphStateKeys.GRAPH_ROUTE, ROUTE_CONTINUE_PIPELINE);
	}

}
