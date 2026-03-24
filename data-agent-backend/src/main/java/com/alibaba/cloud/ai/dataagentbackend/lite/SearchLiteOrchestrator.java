package com.alibaba.cloud.ai.dataagentbackend.lite;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteRequest;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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

	private static final Logger log = LoggerFactory.getLogger(SearchLiteOrchestrator.class);

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
			log.warn("search-lite 无可用 steps：agentId={}, threadId={}", request.agentId(), threadId);
			return Flux.just(SearchLiteMessages.error(ctx, SearchLiteStage.RESULT, "no steps configured"));
		}

		String stepsDesc = steps.stream()
			.map(s -> s.stage() + ":" + s.getClass().getSimpleName())
			.collect(Collectors.joining(", "));
		int queryLen = request.query() == null ? 0 : request.query().length();
		log.info("search-lite 开始：agentId={}, threadId={}, queryLen={}, steps=[{}]", request.agentId(), threadId,
				queryLen, stepsDesc);

		return runSteps(ctx, state, 0)
			.doFinally(signal -> log.info("search-lite 结束：agentId={}, threadId={}, signal={}", request.agentId(),
					threadId, signal))
			.onErrorResume(error -> {
				String msg = (error == null || error.getMessage() == null) ? "unknown error" : error.getMessage();
				log.warn("search-lite 异常：agentId={}, threadId={}, error={}", request.agentId(), threadId, msg, error);
				return Flux.just(SearchLiteMessages.error(ctx, SearchLiteStage.RESULT, msg));
			});
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

		return Flux.defer(() -> {
			SearchLiteStep step = steps.get(index);
			long startedAt = System.nanoTime();
			log.debug("step 开始：threadId={}, index={}, stage={}, impl={}", ctx.threadId(), index, step.stage(),
					step.getClass().getSimpleName());

			SearchLiteStepResult result;
			try {
				result = step.run(ctx, currentState);
			}
			catch (Exception e) {
				return Flux.error(e);
			}

			return result.messages().concatWith(result.updatedState().doOnNext(updatedState -> {
				long tookMs = (System.nanoTime() - startedAt) / 1_000_000;
				log.debug("step 完成：threadId={}, index={}, stage={}, impl={}, tookMs={}", ctx.threadId(), index,
						step.stage(), step.getClass().getSimpleName(), tookMs);
			}).doOnError(e -> {
				long tookMs = (System.nanoTime() - startedAt) / 1_000_000;
				log.warn("step 失败：threadId={}, index={}, stage={}, impl={}, tookMs={}, error={}", ctx.threadId(), index,
						step.stage(), step.getClass().getSimpleName(), tookMs, e == null ? null : e.getMessage(), e);
			}).defaultIfEmpty(currentState).flatMapMany(updatedState -> runSteps(ctx, updatedState, index + 1)));
		});
	}

}
