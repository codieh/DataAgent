package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStepOutputAdapter;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.trace.SearchLiteTraceRecorder;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

@Component
public class SearchLiteSqlRepairGraphNode extends SearchLiteStepGraphNodeSupport implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteSqlRepairGraphNode.class);

	private final SearchLiteStep sqlRepairStep;

	private final SearchLiteGraphStepOutputAdapter outputAdapter;

	public SearchLiteSqlRepairGraphNode(List<SearchLiteStep> steps,
			SearchLiteGraphStepOutputAdapter outputAdapter, SearchLiteTraceRecorder traceRecorder) {
		super(traceRecorder);
		this.sqlRepairStep = steps.stream()
			.filter(step -> step.stage() == SearchLiteStage.SQL_REPAIR)
			.findFirst()
			.orElseThrow(() -> new IllegalStateException("No SQL_REPAIR step configured for graph node"));
		this.outputAdapter = outputAdapter;
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		log.debug("search-lite graph sql-repair node invoked");
		return executeStep(state, sqlRepairStep, outputAdapter);
	}

}
