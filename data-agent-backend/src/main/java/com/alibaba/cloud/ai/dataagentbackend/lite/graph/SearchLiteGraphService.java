package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.conversation.MultiTurnContextManager;
import com.alibaba.cloud.ai.graph.CompiledGraph;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.RunnableConfig;
import com.alibaba.cloud.ai.graph.StateGraph;
import com.alibaba.cloud.ai.graph.exception.GraphRunnerException;
import com.alibaba.cloud.ai.graph.exception.GraphStateException;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Sinks;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.atomic.AtomicReference;

@Service
public class SearchLiteGraphService {

	private final CompiledGraph compiledGraph;

	private final ExecutorService executor;

	private final SearchLiteGraphMessageEmitter messageEmitter;

	private final SearchLiteGraphMessageNormalizer messageNormalizer;

	private final MultiTurnContextManager multiTurnContextManager;

	public SearchLiteGraphService(StateGraph searchLiteGraph, ExecutorService searchLiteGraphExecutor,
			SearchLiteGraphMessageEmitter messageEmitter, SearchLiteGraphMessageNormalizer messageNormalizer,
			MultiTurnContextManager multiTurnContextManager)
			throws GraphStateException {
		this.compiledGraph = searchLiteGraph.compile();
		this.executor = searchLiteGraphExecutor;
		this.messageEmitter = messageEmitter;
		this.messageNormalizer = messageNormalizer;
		this.multiTurnContextManager = multiTurnContextManager;
	}

	public SearchLiteGraphExecutionResult runInitialGraph(SearchLiteState state) throws GraphRunnerException {
		OverAllState finalState = invokeFinalState(state);
		return toExecutionResult(finalState);
	}

	public void graphStreamProcess(Sinks.Many<SearchLiteMessage> sink, SearchLiteContext context, SearchLiteState state,
			AtomicReference<SearchLiteState> latestState) {
		messageEmitter.register(context.threadId(), sink);
		CompletableFuture.runAsync(() -> {
			try {
				OverAllState finalState = invokeFinalState(state);
				SearchLiteGraphExecutionResult graphResult = toExecutionResult(finalState, false);
				SearchLiteState updatedState = graphResult.state() == null ? state : graphResult.state();
				latestState.set(updatedState);

				if (!"DATA_ANALYSIS".equalsIgnoreCase(updatedState.getIntentClassification())) {
					sink.tryEmitNext(SearchLiteMessages.done(context, SearchLiteStage.RESULT, SearchLiteMessageType.JSON, null,
							Map.of("ok", true, "classification", updatedState.getIntentClassification(),
									"message", "当前问题不进入数据分析主链路")));
				}
				multiTurnContextManager.finishTurn(updatedState);
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

	private OverAllState invokeFinalState(SearchLiteState state) throws GraphRunnerException {
		return compiledGraph.invoke(SearchLiteGraphStateMapper.fromSearchLiteState(state), RunnableConfig.builder().build())
			.orElseThrow();
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
		String message = error == null || error.getMessage() == null ? "unknown error" : error.getMessage();
		sink.tryEmitNext(SearchLiteMessages.error(context, SearchLiteStage.RESULT, message));
		sink.tryEmitComplete();
	}

}
