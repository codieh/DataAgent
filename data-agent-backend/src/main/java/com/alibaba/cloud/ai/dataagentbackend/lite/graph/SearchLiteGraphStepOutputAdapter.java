package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Component
public class SearchLiteGraphStepOutputAdapter {

	private final SearchLiteGraphMessageEmitter messageEmitter;

	public SearchLiteGraphStepOutputAdapter(SearchLiteGraphMessageEmitter messageEmitter) {
		this.messageEmitter = messageEmitter;
	}

	public Map<String, Object> adapt(OverAllStateSnapshot snapshot, SearchLiteStepResult stepResult) {
		SearchLiteState originalState = snapshot.originalState();
		SearchLiteState updatedState = stepResult.updatedState().defaultIfEmpty(originalState).block();
		List<SearchLiteMessage> existingMessages = snapshot.existingMessages();
		List<SearchLiteMessage> stepMessages = stepResult.messages().collectList().block();

		Map<String, Object> mappedState = SearchLiteGraphStateMapper
			.fromSearchLiteState(updatedState == null ? originalState : updatedState);

		boolean emittedDirectly = messageEmitter.emit(snapshot.threadId(), stepMessages);
		if (!emittedDirectly) {
			ArrayList<SearchLiteMessage> mergedMessages = new ArrayList<>(existingMessages);
			if (stepMessages != null && !stepMessages.isEmpty()) {
				mergedMessages.addAll(stepMessages);
			}
			mappedState.put(SearchLiteGraphStateKeys.GRAPH_MESSAGES, mergedMessages);
		}
		return mappedState;
	}

	public record OverAllStateSnapshot(String threadId, SearchLiteState originalState, List<SearchLiteMessage> existingMessages) {
	}

}
