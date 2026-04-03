package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class SearchLiteGraphMessageEmitter {

	private final ConcurrentHashMap<String, Sinks.Many<SearchLiteMessage>> sinkMap = new ConcurrentHashMap<>();

	private final SearchLiteGraphMessageNormalizer messageNormalizer;

	public SearchLiteGraphMessageEmitter(SearchLiteGraphMessageNormalizer messageNormalizer) {
		this.messageNormalizer = messageNormalizer;
	}

	public void register(String threadId, Sinks.Many<SearchLiteMessage> sink) {
		if (threadId == null || threadId.isBlank() || sink == null) {
			return;
		}
		sinkMap.put(threadId, sink);
	}

	public void unregister(String threadId) {
		if (threadId == null || threadId.isBlank()) {
			return;
		}
		sinkMap.remove(threadId);
	}

	public boolean hasSink(String threadId) {
		return threadId != null && !threadId.isBlank() && sinkMap.containsKey(threadId);
	}

	public boolean emitOne(String threadId, SearchLiteMessage message) {
		if (threadId == null || threadId.isBlank() || message == null) {
			return false;
		}
		SearchLiteMessage normalizedMessage = messageNormalizer.normalizeMessage(message);
		return emitNormalized(threadId, normalizedMessage);
	}

	public boolean emit(String threadId, List<SearchLiteMessage> messages) {
		if (threadId == null || threadId.isBlank() || messages == null || messages.isEmpty()) {
			return false;
		}
		Sinks.Many<SearchLiteMessage> sink = sinkMap.get(threadId);
		if (sink == null) {
			return false;
		}
		boolean emitted = false;
		for (SearchLiteMessage message : messageNormalizer.normalizeMessages(messages)) {
			if (message == null) {
				continue;
			}
			Sinks.EmitResult result = sink.tryEmitNext(message);
			if (result.isFailure()) {
				return emitted;
			}
			emitted = true;
		}
		return emitted;
	}

	public void emitStream(String threadId, Flux<SearchLiteMessage> messageFlux) {
		if (threadId == null || threadId.isBlank() || messageFlux == null) {
			return;
		}
		if (!hasSink(threadId)) {
			return;
		}
		messageFlux.map(messageNormalizer::normalizeMessage)
			.filter(message -> message != null)
			.doOnNext(message -> emitNormalized(threadId, message))
			.blockLast();
	}

	private boolean emitNormalized(String threadId, SearchLiteMessage message) {
		if (threadId == null || threadId.isBlank() || message == null) {
			return false;
		}
		Sinks.Many<SearchLiteMessage> sink = sinkMap.get(threadId);
		if (sink == null) {
			return false;
		}
		return !sink.tryEmitNext(message).isFailure();
	}

}
