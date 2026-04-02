package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageEmitter;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.impl.ResultMinimaxStep;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class SearchLiteResultGraphNode extends SearchLiteStepGraphNodeSupport implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteResultGraphNode.class);

	private final ResultMinimaxStep resultStep;

	private final SearchLiteGraphMessageEmitter messageEmitter;

	public SearchLiteResultGraphNode(ResultMinimaxStep resultStep, SearchLiteGraphMessageEmitter messageEmitter) {
		this.resultStep = resultStep;
		this.messageEmitter = messageEmitter;
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		log.debug("search-lite graph result node invoked");
		return executeStep(state, resultStep, messageEmitter);
	}

}
