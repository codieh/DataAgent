package com.alibaba.cloud.ai.dataagentbackend.lite.step;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public record SearchLiteStepResult(Flux<SearchLiteMessage> messages, Mono<SearchLiteState> updatedState) {
	public SearchLiteStepResult {
		messages = messages == null ? Flux.empty() : messages;
		updatedState = updatedState == null ? Mono.empty() : updatedState;
	}
}

