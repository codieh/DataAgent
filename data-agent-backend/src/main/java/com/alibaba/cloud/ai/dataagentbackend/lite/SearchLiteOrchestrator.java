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

/**
 * {@code search-lite} 流水线编排器。
 * <p>
 * 流水线定义方式：Spring 会把所有实现了 {@link SearchLiteStep} 的 Bean 收集为一个 {@code List}，并按 {@code @Order} 排序。
 * 本类按顺序执行每个 Step，并把 Step 的消息流拼接为一个总的 SSE 输出流。
 */
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

	/**
	 * 顺序执行 Step。
	 * <p>
	 * 注意：这是一个 {@link Flux}，只有当 WebFlux 为了写 HTTP 响应而订阅（subscribe）时，才会真正开始执行。
	 */
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
