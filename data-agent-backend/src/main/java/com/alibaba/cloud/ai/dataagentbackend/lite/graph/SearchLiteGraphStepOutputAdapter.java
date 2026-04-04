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

	public boolean hasLiveSink(String threadId) {
		return messageEmitter.hasSink(threadId);
	}

	public Map<String, Object> adapt(OverAllStateSnapshot snapshot, SearchLiteStepResult stepResult) {
		SearchLiteState originalState = snapshot.originalState();
		SearchLiteState updatedState = stepResult.updatedState().defaultIfEmpty(originalState).block();
		Map<String, Object> mappedState = SearchLiteGraphStateMapper
			.fromSearchLiteState(updatedState == null ? originalState : updatedState);
		SearchLiteGraphMessageEmitter.DispatchResult dispatchResult = messageEmitter.dispatch(snapshot.threadId(),
				stepResult.messages());

		if (dispatchResult.emittedToSink()) {
			mappedState.remove(SearchLiteGraphStateKeys.GRAPH_MESSAGES);
		}
		else {
			List<SearchLiteMessage> existingMessages = snapshot.existingMessages();
			ArrayList<SearchLiteMessage> mergedMessages = new ArrayList<>(existingMessages);
			List<SearchLiteMessage> bufferedMessages = dispatchResult.bufferedMessages();
			if (bufferedMessages != null && !bufferedMessages.isEmpty()) {
				mergedMessages.addAll(bufferedMessages);
			}
			mappedState.put(SearchLiteGraphStateKeys.GRAPH_MESSAGES, mergedMessages);
		}
		return mappedState;
	}

	public record OverAllStateSnapshot(String threadId, SearchLiteState originalState, List<SearchLiteMessage> existingMessages) {
	}

}
