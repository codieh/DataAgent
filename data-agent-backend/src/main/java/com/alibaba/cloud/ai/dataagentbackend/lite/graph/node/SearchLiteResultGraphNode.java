package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class SearchLiteResultGraphNode implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteResultGraphNode.class);

	@Override
	public Map<String, Object> apply(OverAllState state) {
		log.debug("search-lite graph result node invoked");
		return Map.of();
	}

}
