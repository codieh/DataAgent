package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStepOutputAdapter;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateMapper;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.alibaba.cloud.ai.graph.OverAllState;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;

abstract class SearchLiteStepGraphNodeSupport {

	protected Map<String, Object> executeStep(OverAllState graphState, SearchLiteStep step,
			SearchLiteGraphStepOutputAdapter outputAdapter) {
		SearchLiteState liteState = SearchLiteGraphStateMapper.toSearchLiteState(graphState);
		String threadId = resolveThreadId(liteState);
		SearchLiteContext context = new SearchLiteContext(threadId);
		SearchLiteStepResult stepResult = step.run(context, liteState);
		List<SearchLiteMessage> existingMessages = shouldReadFallbackMessages(outputAdapter, threadId) ? readMessages(graphState)
				: List.of();
		return outputAdapter.adapt(new SearchLiteGraphStepOutputAdapter.OverAllStateSnapshot(threadId, liteState, existingMessages),
				stepResult);
	}

	private boolean shouldReadFallbackMessages(SearchLiteGraphStepOutputAdapter outputAdapter, String threadId) {
		return !outputAdapter.hasLiveSink(threadId);
	}

	private String resolveThreadId(SearchLiteState state) {
		if (StringUtils.hasText(state.getThreadId())) {
			return state.getThreadId();
		}
		String generatedThreadId = "graph-" + UUID.randomUUID();
		state.setThreadId(generatedThreadId);
		return generatedThreadId;
	}

	@SuppressWarnings("unchecked")
	private List<SearchLiteMessage> readMessages(OverAllState graphState) {
		return graphState.value(SearchLiteGraphStateKeys.GRAPH_MESSAGES)
			.filter(List.class::isInstance)
			.map(List.class::cast)
			.map(list -> (List<SearchLiteMessage>) list)
			.orElseGet(ArrayList::new);
	}

}
