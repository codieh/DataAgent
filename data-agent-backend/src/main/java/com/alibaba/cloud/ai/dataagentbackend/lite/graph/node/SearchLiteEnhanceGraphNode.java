package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

@Component
public class SearchLiteEnhanceGraphNode extends SearchLiteStepGraphNodeSupport implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteEnhanceGraphNode.class);

	private final SearchLiteStep enhanceStep;

	public SearchLiteEnhanceGraphNode(List<SearchLiteStep> steps) {
		this.enhanceStep = steps.stream()
			.filter(step -> step.stage() == SearchLiteStage.ENHANCE)
			.findFirst()
			.orElseThrow(() -> new IllegalStateException("No ENHANCE step configured for graph node"));
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		log.debug("search-lite graph enhance node invoked");
		return executeStep(state, enhanceStep);
	}

}
