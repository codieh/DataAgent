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
public class SearchLiteSqlExecuteGraphNode extends SearchLiteStepGraphNodeSupport implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteSqlExecuteGraphNode.class);

	private final SearchLiteStep sqlExecuteStep;

	public SearchLiteSqlExecuteGraphNode(List<SearchLiteStep> steps) {
		this.sqlExecuteStep = steps.stream()
			.filter(step -> step.stage() == SearchLiteStage.SQL_EXECUTE)
			.findFirst()
			.orElseThrow(() -> new IllegalStateException("No SQL_EXECUTE step configured for graph node"));
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		log.debug("search-lite graph sql-execute node invoked");
		return executeStep(state, sqlExecuteStep);
	}

}
