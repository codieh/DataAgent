package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Sinks;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class SearchLiteGraphMessageEmitter {

	private final ConcurrentHashMap<String, Sinks.Many<SearchLiteMessage>> sinkMap = new ConcurrentHashMap<>();

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

	public boolean emit(String threadId, List<SearchLiteMessage> messages) {
		if (threadId == null || threadId.isBlank() || messages == null || messages.isEmpty()) {
			return false;
		}
		Sinks.Many<SearchLiteMessage> sink = sinkMap.get(threadId);
		if (sink == null) {
			return false;
		}
		boolean emitted = false;
		for (SearchLiteMessage message : messages) {
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

}
