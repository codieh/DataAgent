package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateMapper;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.alibaba.cloud.ai.graph.OverAllState;
import org.springframework.util.StringUtils;

import java.util.Map;
import java.util.UUID;

abstract class SearchLiteStepGraphNodeSupport {

	protected Map<String, Object> executeStep(OverAllState graphState, SearchLiteStep step) {
		SearchLiteState liteState = SearchLiteGraphStateMapper.toSearchLiteState(graphState);
		SearchLiteContext context = new SearchLiteContext(resolveThreadId(liteState));
		SearchLiteStepResult stepResult = step.run(context, liteState);
		SearchLiteState updatedState = stepResult.updatedState().defaultIfEmpty(liteState).block();
		return SearchLiteGraphStateMapper.fromSearchLiteState(updatedState == null ? liteState : updatedState);
	}

	private String resolveThreadId(SearchLiteState state) {
		if (StringUtils.hasText(state.getThreadId())) {
			return state.getThreadId();
		}
		String generatedThreadId = "graph-" + UUID.randomUUID();
		state.setThreadId(generatedThreadId);
		return generatedThreadId;
	}

}
