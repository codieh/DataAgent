package com.alibaba.cloud.ai.dataagentbackend.lite;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteRequest;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;

@Service
public class SearchLiteOrchestrator {

	private final List<SearchLiteStep> steps;

	public SearchLiteOrchestrator(List<SearchLiteStep> steps) {
		this.steps = steps;
	}

	public Flux<SearchLiteMessage> stream(SearchLiteRequest request) {
		String threadId = StringUtils.hasText(request.threadId()) ? request.threadId() : UUID.randomUUID().toString();
		SearchLiteContext ctx = new SearchLiteContext(threadId);
		SearchLiteState state = SearchLiteState
			.fromRequest(new SearchLiteRequest(request.agentId(), threadId, request.query()));

		if (steps == null || steps.isEmpty()) {
			return Flux.just(SearchLiteMessages.error(ctx, SearchLiteStage.RESULT, "no steps configured"));
		}

		return runSteps(ctx, state, 0).onErrorResume(error -> Flux.just(SearchLiteMessages.error(ctx,
				SearchLiteStage.RESULT, (error == null || error.getMessage() == null) ? "unknown error"
						: error.getMessage())));
	}

	private Flux<SearchLiteMessage> runSteps(SearchLiteContext ctx, SearchLiteState currentState, int index) {
		if (index >= steps.size()) {
			return Flux.empty();
		}

		SearchLiteStep step = steps.get(index);
		SearchLiteStepResult result = step.run(ctx, currentState);
		return result.messages()
			.concatWith(result.updatedState()
				.defaultIfEmpty(currentState)
				.flatMapMany(updatedState -> runSteps(ctx, updatedState, index + 1)));
	}

}
