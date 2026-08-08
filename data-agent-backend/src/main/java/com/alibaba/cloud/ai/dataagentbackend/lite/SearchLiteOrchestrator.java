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
import com.alibaba.cloud.ai.dataagentbackend.lite.trace.SearchLiteTraceRecorder;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Autowired;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

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

	private final SearchLiteTraceRecorder traceRecorder;

	@Autowired
	public SearchLiteOrchestrator(List<SearchLiteStep> steps,
			@Value("${search.lite.orchestrator.mode:pipeline}") String mode, SearchLiteGraphService graphService,
			MultiTurnContextManager multiTurnContextManager, SearchLiteTraceRecorder traceRecorder) {
		this.steps = steps;
		this.mode = mode == null ? "pipeline" : mode.trim().toLowerCase();
		this.graphService = graphService;
		this.multiTurnContextManager = multiTurnContextManager;
		this.traceRecorder = traceRecorder;
	}

	public Flux<SearchLiteMessage> stream(SearchLiteRequest request) {
		PreparedRun preparedRun = prepareRun(request);
		return buildExecutionFlux(preparedRun);
	}

	public Mono<SearchLiteRunResult> runForEvaluation(SearchLiteRequest request) {
		PreparedRun preparedRun = prepareRun(request);
		long startedAt = System.nanoTime();
		return buildExecutionFlux(preparedRun).collectList().map(messages -> {
			SearchLiteState finalState = finalizeEvaluationState(preparedRun.latestState().get(), messages);
			preparedRun.latestState().set(finalState);
			return new SearchLiteRunResult(
					preparedRun.threadId(),
					finalState,
					messages,
					Duration.ofNanos(System.nanoTime() - startedAt).toMillis());
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
				if (traceRecorder != null) {
					traceRecorder.recordStage(ctx.threadId(), step.stage(), "pipeline-step",
							(System.nanoTime() - startedAt) / 1_000_000, currentState, currentState,
							e == null ? null : e.getMessage());
				}
				return Flux.error(e);
			}

			return result.messages().concatWith(result.updatedState().doOnNext(updatedState -> {
				latestState.set(updatedState);
				long tookMs = (System.nanoTime() - startedAt) / 1_000_000;
				if (traceRecorder != null) {
					traceRecorder.recordStage(ctx.threadId(), step.stage(), "pipeline-step", tookMs, currentState, updatedState,
							null);
				}
				log.debug("step 完成：threadId={}, index={}, stage={}, impl={}, tookMs={}", ctx.threadId(), index,
						step.stage(), step.getClass().getSimpleName(), tookMs);
			}).doOnError(e -> {
				long tookMs = (System.nanoTime() - startedAt) / 1_000_000;
				if (traceRecorder != null) {
					traceRecorder.recordStage(ctx.threadId(), step.stage(), "pipeline-step", tookMs, currentState, currentState,
							e == null ? null : e.getMessage());
				}
				log.warn("step 失败：threadId={}, index={}, stage={}, impl={}, tookMs={}, error={}", ctx.threadId(), index,
						step.stage(), step.getClass().getSimpleName(), tookMs, e == null ? null : e.getMessage(), e);
			}).defaultIfEmpty(currentState)
				.flatMapMany(updatedState -> runSteps(ctx, updatedState, index + 1, latestState)));
		});
	}

	private PreparedRun prepareRun(SearchLiteRequest request) {
		String threadId = StringUtils.hasText(request.threadId()) ? request.threadId() : UUID.randomUUID().toString();
		SearchLiteContext ctx = new SearchLiteContext(threadId);
		boolean feedbackResume = request.hasHumanFeedback() && graphService != null;
		SearchLiteState state = null;
		boolean manageConversation = !feedbackResume;
		if (!feedbackResume) {
			state = SearchLiteState.fromRequest(
					new SearchLiteRequest(request.agentId(), threadId, request.query(), request.humanReviewEnabled(),
							request.humanFeedbackApproved(), request.humanFeedbackComment()));
			PreparedConversationContext preparedConversationContext = multiTurnContextManager.prepareTurn(threadId,
					request.query());
			state.setMultiTurnContext(preparedConversationContext.multiTurnContext());
			state.setContextualizedQuery(preparedConversationContext.contextualizedQuery());
		}
		else {
			state = SearchLiteState.fromRequest(
					new SearchLiteRequest(request.agentId(), threadId, request.query(), request.humanReviewEnabled(),
							request.humanFeedbackApproved(), request.humanFeedbackComment()));
			state.setAwaitingHumanFeedback(false);
			state.setPlanFinished(false);
			state.setPlanFinishedReason(null);
			state.setResultMode(null);
			state.setError(null);
		}
		AtomicReference<SearchLiteState> latestState = new AtomicReference<>(state);
		AtomicBoolean completed = new AtomicBoolean(false);
		if (traceRecorder != null) {
			traceRecorder.startRun(threadId, request.agentId(), request.query(), mode, feedbackResume);
		}
		return new PreparedRun(request, threadId, ctx, state, latestState, completed, manageConversation);
	}

	private Flux<SearchLiteMessage> buildExecutionFlux(PreparedRun preparedRun) {
		if (steps == null || steps.isEmpty()) {
			log.warn("search-lite 无可用 steps：agentId={}, threadId={}", preparedRun.request().agentId(),
					preparedRun.threadId());
			return Flux.just(SearchLiteMessages.error(preparedRun.context(), SearchLiteStage.RESULT, "no steps configured"));
		}

		String stepsDesc = steps.stream()
			.map(s -> s.stage() + ":" + s.getClass().getSimpleName())
			.collect(Collectors.joining(", "));
		int queryLen = preparedRun.request().query() == null ? 0 : preparedRun.request().query().length();
		log.info("search-lite 开始：agentId={}, threadId={}, queryLen={}, steps=[{}]", preparedRun.request().agentId(),
				preparedRun.threadId(), queryLen, stepsDesc);

		Flux<SearchLiteMessage> execution = runWithSelectedMode(preparedRun.context(), preparedRun.state(),
				preparedRun.latestState())
			.doOnComplete(() -> {
				preparedRun.completed().set(true);
				SearchLiteState latest = preparedRun.latestState().get();
				if (preparedRun.manageConversation() && (latest == null || !latest.isAwaitingHumanFeedback())) {
					multiTurnContextManager.finishTurn(latest);
				}
			})
			.doFinally(signal -> log.info("search-lite 结束：agentId={}, threadId={}, signal={}",
					preparedRun.request().agentId(), preparedRun.threadId(), signal))
			.doFinally(signal -> {
				if (!preparedRun.completed().get() && preparedRun.manageConversation()) {
					multiTurnContextManager.discardPending(preparedRun.threadId());
				}
			})
			.onErrorResume(error -> {
				String msg = (error == null || error.getMessage() == null) ? "unknown error" : error.getMessage();
				SearchLiteState latest = preparedRun.latestState().get();
				if (latest != null) {
					latest.setError(msg);
				}
				log.warn("search-lite 异常：agentId={}, threadId={}, error={}", preparedRun.request().agentId(),
						preparedRun.threadId(), msg, error);
				return Flux.just(SearchLiteMessages.error(preparedRun.context(), SearchLiteStage.RESULT, msg));
			});
		return execution.doFinally(signal -> {
			if (traceRecorder != null) {
				traceRecorder.finishRun(preparedRun.threadId(), preparedRun.latestState().get(), String.valueOf(signal));
			}
		});
	}

	private record PreparedRun(SearchLiteRequest request, String threadId, SearchLiteContext context, SearchLiteState state,
			AtomicReference<SearchLiteState> latestState, AtomicBoolean completed, boolean manageConversation) {
	}

	private SearchLiteState finalizeEvaluationState(SearchLiteState state, List<SearchLiteMessage> messages) {
		SearchLiteState target = state == null ? new SearchLiteState() : state;
		List<SearchLiteMessage> safeMessages = messages == null ? List.of() : messages;
		for (SearchLiteMessage message : safeMessages) {
			if (message == null) {
				continue;
			}
			if (StringUtils.hasText(message.error())) {
				target.setError(message.error());
				if (!StringUtils.hasText(target.getResultMode())) {
					target.setResultMode("execution_error");
				}
				continue;
			}
			Map<String, Object> payload = asMap(message.payload());
			switch (message.stage()) {
				case INTENT -> {
					String classification = firstNonBlank(stringValue(payload.get("classification")),
							normalizeIntentLiteral(message.chunk()));
					if (StringUtils.hasText(classification) && !StringUtils.hasText(target.getIntentClassification())) {
						target.setIntentClassification(classification);
					}
				}
				case SCHEMA_RECALL -> {
					List<String> recalledTables = stringList(payload.get("recalledTables"));
					if (!recalledTables.isEmpty() && (target.getRecalledTables() == null || target.getRecalledTables().isEmpty())) {
						target.setRecalledTables(recalledTables);
					}
				}
				case ENHANCE -> {
					String canonicalQuery = stringValue(payload.get("canonicalQuery"));
					if (StringUtils.hasText(canonicalQuery) && !StringUtils.hasText(target.getCanonicalQuery())) {
						target.setCanonicalQuery(canonicalQuery);
					}
				}
				case SQL_GENERATE -> {
					String sql = firstNonBlank(stringValue(payload.get("sql")), message.chunk());
					if (StringUtils.hasText(sql) && !StringUtils.hasText(target.getSql())) {
						target.setSql(sql);
					}
				}
				case SQL_EXECUTE -> {
					List<Map<String, Object>> rows = rowList(payload.get("rows"));
					if (!rows.isEmpty() && (target.getRows() == null || target.getRows().isEmpty())) {
						target.setRows(rows);
					}
				}
				case RESULT -> {
					String resultMode = stringValue(payload.get("resultMode"));
					if (StringUtils.hasText(resultMode) && !StringUtils.hasText(target.getResultMode())) {
						target.setResultMode(resultMode);
					}
					String resultSummary = firstNonBlank(stringValue(payload.get("summary")), message.chunk());
					if (StringUtils.hasText(resultSummary) && !StringUtils.hasText(target.getResultSummary())) {
						target.setResultSummary(resultSummary);
					}
				}
				case HUMAN_FEEDBACK -> {
					String status = stringValue(payload.get("status"));
					if ("WAITING".equalsIgnoreCase(status)) {
						target.setAwaitingHumanFeedback(true);
						if (!StringUtils.hasText(target.getResultMode())) {
							target.setResultMode("waiting_human_feedback");
						}
					}
				}
				default -> {
				}
			}
		}
		return target;
	}

	private Map<String, Object> asMap(Object payload) {
		if (!(payload instanceof Map<?, ?> map)) {
			return Map.of();
		}
		LinkedHashMap<String, Object> normalized = new LinkedHashMap<>();
		for (Map.Entry<?, ?> entry : map.entrySet()) {
			normalized.put(String.valueOf(entry.getKey()), entry.getValue());
		}
		return normalized;
	}

	private List<String> stringList(Object value) {
		if (!(value instanceof List<?> list)) {
			return List.of();
		}
		List<String> values = new ArrayList<>();
		for (Object item : list) {
			String text = stringValue(item);
			if (StringUtils.hasText(text)) {
				values.add(text);
			}
		}
		return values;
	}

	@SuppressWarnings("unchecked")
	private List<Map<String, Object>> rowList(Object value) {
		if (!(value instanceof List<?> list)) {
			return List.of();
		}
		List<Map<String, Object>> rows = new ArrayList<>();
		for (Object item : list) {
			if (item instanceof Map<?, ?> map) {
				LinkedHashMap<String, Object> row = new LinkedHashMap<>();
				for (Map.Entry<?, ?> entry : map.entrySet()) {
					row.put(String.valueOf(entry.getKey()), entry.getValue());
				}
				rows.add((Map<String, Object>) row);
			}
		}
		return rows;
	}

	private String stringValue(Object value) {
		return value == null ? null : String.valueOf(value);
	}

	private String firstNonBlank(String... values) {
		if (values == null) {
			return null;
		}
		for (String value : values) {
			if (StringUtils.hasText(value)) {
				return value;
			}
		}
		return null;
	}

	private String normalizeIntentLiteral(String value) {
		if (!StringUtils.hasText(value)) {
			return null;
		}
		String normalized = value.trim();
		if ("DATA_ANALYSIS".equalsIgnoreCase(normalized) || "CHITCHAT".equalsIgnoreCase(normalized)) {
			return normalized.toUpperCase(java.util.Locale.ROOT);
		}
		return null;
	}

}
