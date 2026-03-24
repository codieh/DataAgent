package com.alibaba.cloud.ai.dataagentbackend.controller;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteRequest;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteOrchestrator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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

	private static final Logger log = LoggerFactory.getLogger(SearchLiteController.class);

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

		int queryLen = query == null ? 0 : query.length();
		log.info("SSE 请求：/api/stream/search-lite agentId={}, threadId={}, queryLen={}", agentId, threadId, queryLen);

		return orchestrator.stream(new SearchLiteRequest(agentId, threadId, query))
			.map(this::toSse)
			.doOnSubscribe(s -> log.info("SSE 已订阅：agentId={}, threadId={}", agentId, threadId))
			.doOnCancel(() -> log.info("SSE 已取消：agentId={}, threadId={}", agentId, threadId))
			.doFinally(signal -> log.info("SSE 结束：agentId={}, threadId={}, signal={}", agentId, threadId, signal));
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
