package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.lite.step.impl.IntentMinimaxStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageEmitter;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class SearchLiteIntentGraphNode extends SearchLiteStepGraphNodeSupport implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteIntentGraphNode.class);

	private final IntentMinimaxStep intentStep;

	private final SearchLiteGraphMessageEmitter messageEmitter;

	public SearchLiteIntentGraphNode(IntentMinimaxStep intentStep, SearchLiteGraphMessageEmitter messageEmitter) {
		this.intentStep = intentStep;
		this.messageEmitter = messageEmitter;
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		log.debug("search-lite graph intent node invoked");
		return executeStep(state, intentStep, messageEmitter);
	}

}
