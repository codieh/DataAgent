package com.alibaba.cloud.ai.dataagentbackend.lite;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteRequest;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.conversation.MultiTurnContextManager;
import com.alibaba.cloud.ai.dataagentbackend.lite.conversation.PreparedConversationContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphService;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
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

	private final String mode;

	private final SearchLiteGraphService graphService;

	private final MultiTurnContextManager multiTurnContextManager;

	public SearchLiteOrchestrator(List<SearchLiteStep> steps) {
		this(steps, "pipeline", null, new MultiTurnContextManager(5, 240));
	}

	public SearchLiteOrchestrator(List<SearchLiteStep> steps,
			@Value("${search.lite.orchestrator.mode:pipeline}") String mode, SearchLiteGraphService graphService,
			MultiTurnContextManager multiTurnContextManager) {
		this.steps = steps;
		this.mode = mode == null ? "pipeline" : mode.trim().toLowerCase();
		this.graphService = graphService;
		this.multiTurnContextManager = multiTurnContextManager;
	}

	public Flux<SearchLiteMessage> stream(SearchLiteRequest request) {
		String threadId = StringUtils.hasText(request.threadId()) ? request.threadId() : UUID.randomUUID().toString();
		SearchLiteContext ctx = new SearchLiteContext(threadId);
		SearchLiteState state = SearchLiteState
			.fromRequest(new SearchLiteRequest(request.agentId(), threadId, request.query()));
		PreparedConversationContext preparedConversationContext = multiTurnContextManager.prepareTurn(threadId, request.query());
		state.setMultiTurnContext(preparedConversationContext.multiTurnContext());
		state.setContextualizedQuery(preparedConversationContext.contextualizedQuery());
		AtomicReference<SearchLiteState> latestState = new AtomicReference<>(state);
		AtomicBoolean completed = new AtomicBoolean(false);

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

		return runWithSelectedMode(ctx, state, latestState)
			.doOnComplete(() -> {
				completed.set(true);
				multiTurnContextManager.finishTurn(latestState.get());
			})
			.doFinally(signal -> log.info("search-lite 结束：agentId={}, threadId={}, signal={}", request.agentId(),
					threadId, signal))
			.doFinally(signal -> {
				if (!completed.get()) {
					multiTurnContextManager.discardPending(threadId);
				}
			})
			.onErrorResume(error -> {
				String msg = (error == null || error.getMessage() == null) ? "unknown error" : error.getMessage();
				log.warn("search-lite 异常：agentId={}, threadId={}, error={}", request.agentId(), threadId, msg, error);
				return Flux.just(SearchLiteMessages.error(ctx, SearchLiteStage.RESULT, msg));
			});
	}

	private Flux<SearchLiteMessage> runWithSelectedMode(SearchLiteContext ctx, SearchLiteState state,
			AtomicReference<SearchLiteState> latestState) {
		if ("graph".equalsIgnoreCase(mode)) {
			return runGraphMode(ctx, state, latestState);
		}
		return runSteps(ctx, state, 0, latestState);
	}

	private Flux<SearchLiteMessage> runGraphMode(SearchLiteContext ctx, SearchLiteState state,
			AtomicReference<SearchLiteState> latestState) {
		return Flux.defer(() -> {
			log.info("search-lite 使用 graph 编排：threadId={}", ctx.threadId());
			reactor.core.publisher.Sinks.Many<SearchLiteMessage> sink = reactor.core.publisher.Sinks.many()
				.unicast()
				.onBackpressureBuffer();
			graphService.graphStreamProcess(sink, ctx, state, latestState);
			return sink.asFlux();
		});
	}

	/**
	 * 顺序执行 Step。
	 * <p>
	 * 注意：这是一个 {@link Flux}，只有当 WebFlux 为了写 HTTP 响应而订阅（subscribe）时，才会真正开始执行。
	 */
	private Flux<SearchLiteMessage> runSteps(SearchLiteContext ctx, SearchLiteState currentState, int index,
			AtomicReference<SearchLiteState> latestState) {
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
				latestState.set(updatedState);
				long tookMs = (System.nanoTime() - startedAt) / 1_000_000;
				log.debug("step 完成：threadId={}, index={}, stage={}, impl={}, tookMs={}", ctx.threadId(), index,
						step.stage(), step.getClass().getSimpleName(), tookMs);
			}).doOnError(e -> {
				long tookMs = (System.nanoTime() - startedAt) / 1_000_000;
				log.warn("step 失败：threadId={}, index={}, stage={}, impl={}, tookMs={}, error={}", ctx.threadId(), index,
						step.stage(), step.getClass().getSimpleName(), tookMs, e == null ? null : e.getMessage(), e);
			}).defaultIfEmpty(currentState)
				.flatMapMany(updatedState -> runSteps(ctx, updatedState, index + 1, latestState)));
		});
	}

}
