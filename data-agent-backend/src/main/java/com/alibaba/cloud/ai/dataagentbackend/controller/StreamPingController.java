package com.alibaba.cloud.ai.dataagentbackend.controller;

import com.alibaba.cloud.ai.dataagentbackend.api.StreamMessage;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/stream")
public class StreamPingController {

	@GetMapping(value = "/ping", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
	public Flux<ServerSentEvent<StreamMessage>> ping() {
		String threadId = UUID.randomUUID().toString();
		return Flux.interval(Duration.ofMillis(200))
			.take(10)
			.map(seq -> ServerSentEvent.builder(new StreamMessage(threadId, "PING", "pong", seq, Instant.now()))
				.event("message")
				.id(threadId + ":" + seq)
				.build())
			.concatWith(Flux.just(ServerSentEvent.<StreamMessage>builder()
				.event("complete")
				.id(threadId + ":complete")
				.build()));
	}

}

