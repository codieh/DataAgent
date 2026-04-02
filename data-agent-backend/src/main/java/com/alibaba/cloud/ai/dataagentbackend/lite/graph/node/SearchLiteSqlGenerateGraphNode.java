package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageEmitter;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

@Component
public class SearchLiteSqlGenerateGraphNode extends SearchLiteStepGraphNodeSupport implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteSqlGenerateGraphNode.class);

	private final SearchLiteStep sqlGenerateStep;

	private final SearchLiteGraphMessageEmitter messageEmitter;

	public SearchLiteSqlGenerateGraphNode(List<SearchLiteStep> steps, SearchLiteGraphMessageEmitter messageEmitter) {
		this.sqlGenerateStep = steps.stream()
			.filter(step -> step.stage() == SearchLiteStage.SQL_GENERATE)
			.findFirst()
			.orElseThrow(() -> new IllegalStateException("No SQL_GENERATE step configured for graph node"));
		this.messageEmitter = messageEmitter;
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		log.debug("search-lite graph sql-generate node invoked");
		return executeStep(state, sqlGenerateStep, messageEmitter);
	}

}
