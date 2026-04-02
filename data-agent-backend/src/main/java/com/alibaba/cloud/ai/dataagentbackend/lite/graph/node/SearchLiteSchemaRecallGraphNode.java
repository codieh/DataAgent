package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStepOutputAdapter;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

@Component
public class SearchLiteSchemaRecallGraphNode extends SearchLiteStepGraphNodeSupport implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteSchemaRecallGraphNode.class);

	private final SearchLiteStep schemaRecallStep;

	private final SearchLiteGraphStepOutputAdapter outputAdapter;

	public SearchLiteSchemaRecallGraphNode(List<SearchLiteStep> steps, SearchLiteGraphStepOutputAdapter outputAdapter) {
		this.schemaRecallStep = steps.stream()
			.filter(step -> step.stage() == SearchLiteStage.SCHEMA_RECALL)
			.findFirst()
			.orElseThrow(() -> new IllegalStateException("No SCHEMA_RECALL step configured for graph node"));
		this.outputAdapter = outputAdapter;
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		log.debug("search-lite graph schema recall node invoked");
		return executeStep(state, schemaRecallStep, outputAdapter);
	}

}
