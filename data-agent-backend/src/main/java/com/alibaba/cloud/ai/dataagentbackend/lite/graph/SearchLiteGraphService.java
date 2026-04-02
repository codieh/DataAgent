package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteContinueGraphNode;
import com.alibaba.cloud.ai.graph.CompiledGraph;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.RunnableConfig;
import com.alibaba.cloud.ai.graph.StateGraph;
import com.alibaba.cloud.ai.graph.exception.GraphRunnerException;
import com.alibaba.cloud.ai.graph.exception.GraphStateException;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.function.Function;

@Service
public class SearchLiteGraphService {

	private final CompiledGraph compiledGraph;

	private final ExecutorService executor;

	public SearchLiteGraphService(StateGraph searchLiteGraph, ExecutorService searchLiteGraphExecutor)
			throws GraphStateException {
		this.compiledGraph = searchLiteGraph.compile();
		this.executor = searchLiteGraphExecutor;
	}

	public SearchLiteGraphExecutionResult runInitialGraph(SearchLiteState state) throws GraphRunnerException {
		OverAllState finalState = compiledGraph
			.invoke(SearchLiteGraphStateMapper.fromSearchLiteState(state), RunnableConfig.builder().build())
			.orElseThrow();
		SearchLiteState updatedState = SearchLiteGraphStateMapper.toSearchLiteState(finalState);
		List<SearchLiteMessage> messages = finalState.value(SearchLiteGraphStateKeys.GRAPH_MESSAGES)
			.filter(List.class::isInstance)
			.map(List.class::cast)
			.map(list -> (List<SearchLiteMessage>) list)
			.orElse(List.of());
		String route = finalState.value(SearchLiteGraphStateKeys.GRAPH_ROUTE)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.orElse("");
		return new SearchLiteGraphExecutionResult(updatedState, messages, route);
	}

	public void graphStreamProcess(Sinks.Many<SearchLiteMessage> sink, SearchLiteContext context, SearchLiteState state,
			Function<SearchLiteState, Flux<SearchLiteMessage>> continueWithPipeline) {
		CompletableFuture.runAsync(() -> {
			try {
				SearchLiteGraphExecutionResult graphResult = runInitialGraph(state);
				emitMessages(sink, graphResult.messages());
				SearchLiteState updatedState = graphResult.state() == null ? state : graphResult.state();

				if (SearchLiteContinueGraphNode.ROUTE_CONTINUE_PIPELINE.equals(graphResult.route())) {
					continueWithPipeline.apply(updatedState)
						.subscribe(message -> sink.tryEmitNext(message), error -> emitError(sink, context, error),
								() -> sink.tryEmitComplete());
					return;
				}

				sink.tryEmitNext(SearchLiteMessages.done(context, SearchLiteStage.RESULT, SearchLiteMessageType.JSON, null,
						Map.of("ok", true, "classification", updatedState.getIntentClassification(),
								"message", "当前问题不进入数据分析主链路")));
				sink.tryEmitComplete();
			}
			catch (Exception e) {
				emitError(sink, context, e);
			}
		}, executor);
	}

	private void emitMessages(Sinks.Many<SearchLiteMessage> sink, List<SearchLiteMessage> messages) {
		if (messages == null || messages.isEmpty()) {
			return;
		}
		for (SearchLiteMessage message : messages) {
			sink.tryEmitNext(message);
		}
	}

	private void emitError(Sinks.Many<SearchLiteMessage> sink, SearchLiteContext context, Throwable error) {
		String message = error == null || error.getMessage() == null ? "unknown error" : error.getMessage();
		sink.tryEmitNext(SearchLiteMessages.error(context, SearchLiteStage.RESULT, message));
		sink.tryEmitComplete();
	}

}
