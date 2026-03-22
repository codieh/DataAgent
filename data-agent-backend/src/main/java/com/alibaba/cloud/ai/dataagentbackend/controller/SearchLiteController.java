package com.alibaba.cloud.ai.dataagentbackend.controller;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteRequest;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteOrchestrator;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@CrossOrigin(origins = "*")
@RequestMapping("/api/stream")
public class SearchLiteController {

	private final SearchLiteOrchestrator orchestrator;

	public SearchLiteController(SearchLiteOrchestrator orchestrator) {
		this.orchestrator = orchestrator;
	}

	@GetMapping(value = "/search-lite", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
	public Flux<ServerSentEvent<SearchLiteMessage>> searchLite(@RequestParam("agentId") String agentId,
			@RequestParam(value = "threadId", required = false) String threadId, @RequestParam("query") String query,
			ServerHttpResponse response) {
		response.getHeaders().add("Cache-Control", "no-cache");
		response.getHeaders().add("Connection", "keep-alive");
		response.getHeaders().add("Access-Control-Allow-Origin", "*");

		return orchestrator.stream(new SearchLiteRequest(agentId, threadId, query)).map(this::toSse);
	}

	private ServerSentEvent<SearchLiteMessage> toSse(SearchLiteMessage message) {
		String event;
		if (message.error() != null && !message.error().isBlank()) {
			event = "error";
		}
		else if (message.done()) {
			event = "complete";
		}
		else {
			event = "message";
		}

		return ServerSentEvent.builder(message).event(event).id(message.threadId() + ":" + message.seq()).build();
	}

}

