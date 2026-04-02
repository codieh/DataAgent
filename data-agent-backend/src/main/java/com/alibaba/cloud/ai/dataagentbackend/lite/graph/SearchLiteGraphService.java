package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.graph.CompiledGraph;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.RunnableConfig;
import com.alibaba.cloud.ai.graph.StateGraph;
import com.alibaba.cloud.ai.graph.exception.GraphRunnerException;
import com.alibaba.cloud.ai.graph.exception.GraphStateException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Sinks;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;

@Service
public class SearchLiteGraphService {

	private final CompiledGraph compiledGraph;

	private final ExecutorService executor;

	private final ObjectMapper objectMapper;

	private final SearchLiteGraphMessageEmitter messageEmitter;

	public SearchLiteGraphService(StateGraph searchLiteGraph, ExecutorService searchLiteGraphExecutor,
			ObjectMapper objectMapper, SearchLiteGraphMessageEmitter messageEmitter)
			throws GraphStateException {
		this.compiledGraph = searchLiteGraph.compile();
		this.executor = searchLiteGraphExecutor;
		this.objectMapper = objectMapper;
		this.messageEmitter = messageEmitter;
	}

	public SearchLiteGraphExecutionResult runInitialGraph(SearchLiteState state) throws GraphRunnerException {
		OverAllState finalState = compiledGraph
			.invoke(SearchLiteGraphStateMapper.fromSearchLiteState(state), RunnableConfig.builder().build())
			.orElseThrow();
		SearchLiteState updatedState = SearchLiteGraphStateMapper.toSearchLiteState(finalState);
		List<SearchLiteMessage> messages = finalState.value(SearchLiteGraphStateKeys.GRAPH_MESSAGES)
			.filter(List.class::isInstance)
			.map(List.class::cast)
			.map(this::normalizeMessages)
			.orElse(List.of());
		String route = finalState.value(SearchLiteGraphStateKeys.GRAPH_ROUTE)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.orElse("");
		return new SearchLiteGraphExecutionResult(updatedState, messages, route);
	}

	public void graphStreamProcess(Sinks.Many<SearchLiteMessage> sink, SearchLiteContext context, SearchLiteState state) {
		messageEmitter.register(context.threadId(), sink);
		CompletableFuture.runAsync(() -> {
			try {
				SearchLiteGraphExecutionResult graphResult = runInitialGraph(state);
				emitMessages(sink, graphResult.messages());
				SearchLiteState updatedState = graphResult.state() == null ? state : graphResult.state();

				if (!"DATA_ANALYSIS".equalsIgnoreCase(updatedState.getIntentClassification())) {
					sink.tryEmitNext(SearchLiteMessages.done(context, SearchLiteStage.RESULT, SearchLiteMessageType.JSON, null,
							Map.of("ok", true, "classification", updatedState.getIntentClassification(),
									"message", "当前问题不进入数据分析主链路")));
				}
				sink.tryEmitComplete();
			}
			catch (Exception e) {
				emitError(sink, context, e);
			}
			finally {
				messageEmitter.unregister(context.threadId());
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

	private List<SearchLiteMessage> normalizeMessages(List<?> rawMessages) {
		if (rawMessages == null || rawMessages.isEmpty()) {
			return List.of();
		}
		List<SearchLiteMessage> normalized = new ArrayList<>(rawMessages.size());
		for (Object rawMessage : rawMessages) {
			SearchLiteMessage message = normalizeMessage(rawMessage);
			if (message != null) {
				normalized.add(message);
			}
		}
		return normalized;
	}

	private SearchLiteMessage normalizeMessage(Object rawMessage) {
		if (rawMessage == null) {
			return null;
		}
		SearchLiteMessage message = rawMessage instanceof SearchLiteMessage searchLiteMessage ? searchLiteMessage
				: objectMapper.convertValue(rawMessage, SearchLiteMessage.class);
		Object normalizedPayload = normalizePayload(message.payload());
		return new SearchLiteMessage(message.threadId(), message.stage(), message.type(), message.chunk(), normalizedPayload,
				message.done(), message.error(), message.seq(), message.timestamp() == null ? Instant.now() : message.timestamp());
	}

	private Object normalizePayload(Object payload) {
		if (payload == null) {
			return null;
		}
		if (payload instanceof String || payload instanceof Number || payload instanceof Boolean) {
			return payload;
		}
		if (payload instanceof Map<?, ?> map) {
			LinkedHashMap<String, Object> normalized = new LinkedHashMap<>();
			for (Map.Entry<?, ?> entry : map.entrySet()) {
				normalized.put(String.valueOf(entry.getKey()), normalizePayload(entry.getValue()));
			}
			return normalized;
		}
		if (payload instanceof List<?> list) {
			List<Object> normalized = new ArrayList<>(list.size());
			for (Object item : list) {
				normalized.add(normalizePayload(item));
			}
			return normalized;
		}
		try {
			return objectMapper.readValue(objectMapper.writeValueAsBytes(payload), Object.class);
		}
		catch (Exception e) {
			try {
				Map<?, ?> converted = objectMapper.convertValue(payload, Map.class);
				return normalizePayload(converted);
			}
			catch (Exception ignored) {
				try {
					return objectMapper.convertValue(objectMapper.valueToTree(payload), Object.class);
				}
				catch (Exception ignoredAgain) {
					return String.valueOf(payload);
				}
			}
		}
	}

}
