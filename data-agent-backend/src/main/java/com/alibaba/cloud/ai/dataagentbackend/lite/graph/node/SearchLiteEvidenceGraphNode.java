package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStepOutputAdapter;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.impl.EvidenceFileStep;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class SearchLiteEvidenceGraphNode extends SearchLiteStepGraphNodeSupport implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteEvidenceGraphNode.class);

	private final EvidenceFileStep evidenceStep;

	private final SearchLiteGraphStepOutputAdapter outputAdapter;

	public SearchLiteEvidenceGraphNode(EvidenceFileStep evidenceStep, SearchLiteGraphStepOutputAdapter outputAdapter) {
		this.evidenceStep = evidenceStep;
		this.outputAdapter = outputAdapter;
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		log.debug("search-lite graph evidence node invoked");
		return executeStep(state, evidenceStep, outputAdapter);
	}

}
