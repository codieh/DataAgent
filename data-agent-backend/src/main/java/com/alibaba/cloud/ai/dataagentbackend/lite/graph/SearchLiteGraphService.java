package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLitePlanStep;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.conversation.MultiTurnContextManager;
import com.alibaba.cloud.ai.graph.CompiledGraph;
import com.alibaba.cloud.ai.graph.CompileConfig;
import com.alibaba.cloud.ai.graph.NodeOutput;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.RunnableConfig;
import com.alibaba.cloud.ai.graph.StateGraph;
import com.alibaba.cloud.ai.graph.exception.GraphRunnerException;
import com.alibaba.cloud.ai.graph.exception.GraphStateException;
import com.alibaba.cloud.ai.graph.state.StateSnapshot;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.atomic.AtomicReference;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.HUMAN_FEEDBACK_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLAN_EXECUTOR_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLANNER_NODE;

@Service
public class SearchLiteGraphService {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteGraphService.class);

	private final CompiledGraph compiledGraph;

	private final ExecutorService executor;

	private final SearchLiteGraphMessageEmitter messageEmitter;

	private final SearchLiteGraphMessageNormalizer messageNormalizer;

	private final MultiTurnContextManager multiTurnContextManager;

	public SearchLiteGraphService(StateGraph searchLiteGraph, ExecutorService searchLiteGraphExecutor,
			SearchLiteGraphMessageEmitter messageEmitter, SearchLiteGraphMessageNormalizer messageNormalizer,
			MultiTurnContextManager multiTurnContextManager)
			throws GraphStateException {
		this.compiledGraph = searchLiteGraph.compile(
				CompileConfig.builder().interruptBefore(HUMAN_FEEDBACK_NODE).build());
		this.executor = searchLiteGraphExecutor;
		this.messageEmitter = messageEmitter;
		this.messageNormalizer = messageNormalizer;
		this.multiTurnContextManager = multiTurnContextManager;
	}

	public SearchLiteGraphExecutionResult runInitialGraph(SearchLiteState state) throws GraphRunnerException {
		OverAllState finalState = invokeInitialState(state);
		return toExecutionResult(finalState);
	}

	public void graphStreamProcess(Sinks.Many<SearchLiteMessage> sink, SearchLiteContext context, SearchLiteState state,
			AtomicReference<SearchLiteState> latestState) {
		messageEmitter.register(context.threadId(), sink);
		CompletableFuture.runAsync(() -> {
			try {
				OverAllState finalState = state.getHumanFeedbackStatus() == null || state.getHumanFeedbackStatus().isBlank()
						? invokeInitialState(state)
						: resumeFinalState(state);
				SearchLiteGraphExecutionResult graphResult = toExecutionResult(finalState, false);
				SearchLiteState updatedState = graphResult.state() == null ? state : graphResult.state();
				if (isWaitingForHumanFeedback(updatedState)) {
					updatedState = markWaitingHumanFeedback(updatedState);
					emitWaiting(context, updatedState);
				}
				latestState.set(updatedState);

				if (!"DATA_ANALYSIS".equalsIgnoreCase(updatedState.getIntentClassification())) {
					sink.tryEmitNext(SearchLiteMessages.done(context, SearchLiteStage.RESULT, SearchLiteMessageType.JSON, null,
							Map.of("ok", true, "classification", updatedState.getIntentClassification(),
									"message", "当前问题不进入数据分析主链路")));
				}
				if (!updatedState.isAwaitingHumanFeedback()) {
					multiTurnContextManager.finishTurn(updatedState);
				}
				sink.tryEmitComplete();
			}
			catch (Exception e) {
				multiTurnContextManager.discardPending(context.threadId());
				emitError(sink, context, e);
			}
			finally {
				messageEmitter.unregister(context.threadId());
			}
		}, executor);
	}

	private OverAllState invokeInitialState(SearchLiteState state) throws GraphRunnerException {
		RunnableConfig config = RunnableConfig.builder().threadId(state.getThreadId()).build();
		NodeOutput lastOutput = compiledGraph.stream(SearchLiteGraphStateMapper.fromSearchLiteState(state), config)
			.blockLast();
		logSnapshot("initial-after-stream", config);
		if (lastOutput != null && lastOutput.state() != null) {
			return lastOutput.state();
		}
		return compiledGraph.getState(config).state();
	}

	private OverAllState resumeFinalState(SearchLiteState state) throws GraphRunnerException {
		String threadId = state.getThreadId();
		String feedbackStatus = state.getHumanFeedbackStatus() == null ? "" : state.getHumanFeedbackStatus();
		String comment = state.getHumanFeedbackComment() == null ? "" : state.getHumanFeedbackComment();
		SearchLiteContext context = new SearchLiteContext(threadId);
		logResume(context, feedbackStatus, comment);
		String nextNode = applyHumanFeedbackResume(state, feedbackStatus, comment);
		emitResumeDecision(context, state, nextNode);
		// Try management-style resume first: updateState + stream(null, config)
		try {
			Map<String, Object> feedbackData = buildFeedbackData(feedbackStatus, comment);
			Map<String, Object> stateUpdate = new HashMap<>();
			stateUpdate.put(SearchLiteGraphStateKeys.HUMAN_FEEDBACK_DATA, feedbackData);
			RunnableConfig baseConfig = RunnableConfig.builder().threadId(threadId).build();
			RunnableConfig updatedConfig = compiledGraph.updateState(baseConfig, stateUpdate);
			RunnableConfig resumeConfig = RunnableConfig.builder(updatedConfig)
				.addMetadata(RunnableConfig.HUMAN_FEEDBACK_METADATA_KEY, feedbackData)
				.build();
			log.info("graph resume (checkpoint): threadId={}, checkpointId={}", threadId,
					resumeConfig.checkPointId().orElse("(none)"));
			Flux<NodeOutput> nodeOutputFlux = compiledGraph.stream(null, resumeConfig);
			NodeOutput lastOutput = nodeOutputFlux.blockLast();
			if (lastOutput != null && lastOutput.state() != null) {
				return lastOutput.state();
			}
			return compiledGraph.getState(resumeConfig).state();
		}
		catch (Exception ex) {
			throw new IllegalStateException("Failed to resume graph for threadId=" + threadId, ex);
		}
	}


	private SearchLiteGraphExecutionResult toExecutionResult(OverAllState finalState) {
		return toExecutionResult(finalState, true);
	}

	private SearchLiteGraphExecutionResult toExecutionResult(OverAllState finalState, boolean includeMessages) {
		SearchLiteState updatedState = SearchLiteGraphStateMapper.toSearchLiteState(finalState);
		List<SearchLiteMessage> messages = includeMessages ? finalState.value(SearchLiteGraphStateKeys.GRAPH_MESSAGES)
			.filter(List.class::isInstance)
			.map(List.class::cast)
			.map(messageNormalizer::normalizeMessages)
			.orElse(List.of()) : List.of();
		String route = finalState.value(SearchLiteGraphStateKeys.GRAPH_ROUTE)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.orElse("");
		return new SearchLiteGraphExecutionResult(updatedState, messages, route);
	}

	private void emitError(Sinks.Many<SearchLiteMessage> sink, SearchLiteContext context, Throwable error) {
		Throwable root = error;
		while (root != null && root.getCause() != null) {
			root = root.getCause();
		}
		String message = root == null || root.getMessage() == null ? "unknown error" : root.getMessage();
		sink.tryEmitNext(SearchLiteMessages.error(context, SearchLiteStage.RESULT, message));
		sink.tryEmitComplete();
	}

	private boolean isWaitingForHumanFeedback(SearchLiteState state) {
		return state != null && state.isHumanReviewEnabled()
				&& (state.getHumanFeedbackStatus() == null || state.getHumanFeedbackStatus().isBlank())
				&& state.getPlanSteps() != null && !state.getPlanSteps().isEmpty() && !state.isPlanFinished();
	}

	private SearchLiteState markWaitingHumanFeedback(SearchLiteState state) {
		state.setAwaitingHumanFeedback(true);
		state.setPlanFinished(true);
		state.setPlanFinishedReason("waiting_human_feedback");
		state.setResultMode("waiting_human_feedback");
		return state;
	}

	private void emitWaiting(SearchLiteContext context, SearchLiteState state) {
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.message(context, SearchLiteStage.HUMAN_FEEDBACK,
				SearchLiteMessageType.TEXT, "计划已生成，等待人工审核。", null));
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.done(context, SearchLiteStage.HUMAN_FEEDBACK,
				SearchLiteMessageType.JSON, null,
				Map.of("status", "WAITING", "steps", state.getPlanSteps() == null ? List.of() : state.getPlanSteps(),
						"message", "请基于 threadId 提交人工审核结果后继续执行。")));
	}

	private void logResume(SearchLiteContext context, String feedbackStatus, String comment) {
		log.info("human feedback resume: threadId={}, status={}, commentLen={}", context.threadId(), feedbackStatus,
				comment == null ? 0 : comment.length());
	}

	private String applyHumanFeedbackResume(SearchLiteState state, String feedbackStatus, String comment) {
		boolean approved = "APPROVED".equalsIgnoreCase(feedbackStatus);
		state.setHumanFeedbackStatus(approved ? "APPROVED" : "REJECTED");
		state.setHumanFeedbackComment(comment == null ? "" : comment.trim());
		state.setAwaitingHumanFeedback(false);
		state.setPlanFinished(false);
		state.setPlanFinishedReason(null);
		state.setResultMode(null);
		state.setError(null);
		if (approved) {
			state.setHumanReviewEnabled(false);
			state.setPlanValidationStatus(true);
			state.setPlanValidationError(null);
			return PLAN_EXECUTOR_NODE;
		}
		state.setHumanReviewEnabled(true);
		state.setPlanValidationStatus(false);
		state.setPlanValidationError(state.getHumanFeedbackComment().isBlank() ? "Plan rejected by human reviewer"
				: state.getHumanFeedbackComment());
		state.setPlanRepairCount(state.getPlanRepairCount() + 1);
		state.setPlannerRawOutput("");
		state.setCurrentPlanStepIndex(0);
		resetPlanSteps(state.getPlanSteps());
		return PLANNER_NODE;
	}

	private void emitResumeDecision(SearchLiteContext context, SearchLiteState state, String nextNode) {
		if (PLAN_EXECUTOR_NODE.equals(nextNode)) {
			messageEmitter.emitOne(context.threadId(), SearchLiteMessages.done(context, SearchLiteStage.HUMAN_FEEDBACK,
					SearchLiteMessageType.JSON, null,
					Map.of("status", "APPROVED", "message", "人工审核已通过，继续执行计划。")));
			return;
		}
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.done(context, SearchLiteStage.HUMAN_FEEDBACK,
				SearchLiteMessageType.JSON, null,
				Map.of("status", "REJECTED", "repairCount", state.getPlanRepairCount(), "comment",
						state.getPlanValidationError() == null ? "" : state.getPlanValidationError(),
						"message", "人工审核已拒绝，准备重新规划。")));
	}

	private void resetPlanSteps(List<SearchLitePlanStep> steps) {
		if (steps == null) {
			return;
		}
		for (SearchLitePlanStep step : steps) {
			if (step == null) {
				continue;
			}
			step.setStatus("PENDING");
			step.setSql(null);
			step.setRowCount(0);
			step.setPreviewRows(List.of());
			step.setError(null);
			step.setSummarySnippet(null);
		}
	}

	private void logSnapshot(String phase, RunnableConfig config) {
		try {
			StateSnapshot snapshot = compiledGraph.getState(config);
			log.info("graph snapshot: phase={}, node={}, nextNode={}, checkpointId={}, threadId={}", phase, snapshot.node(),
					snapshot.next(), snapshot.config().checkPointId().orElse(""), snapshot.config().threadId().orElse(""));
		}
		catch (Exception ex) {
			log.warn("graph snapshot unavailable: phase={}, threadId={}, error={}", phase,
					config.threadId().orElse(""), ex.getMessage());
		}
	}

	private Map<String, Object> buildFeedbackData(String feedbackStatus, String comment) {
		boolean approved = "APPROVED".equalsIgnoreCase(feedbackStatus);
		return Map.of("feedback", approved, "feedback_content", comment == null ? "" : comment);
	}

}
