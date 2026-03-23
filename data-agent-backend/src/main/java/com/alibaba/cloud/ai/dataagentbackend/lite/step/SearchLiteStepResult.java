package com.alibaba.cloud.ai.dataagentbackend.lite.step;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * {@link SearchLiteStep} 的输出。
 * <p>
 * {@code messages} 用于流式输出给前端；{@code updatedState} 是该阶段处理后的状态（给后续 Step 使用）。
 */
public record SearchLiteStepResult(Flux<SearchLiteMessage> messages, Mono<SearchLiteState> updatedState) {
	public SearchLiteStepResult {
		messages = messages == null ? Flux.empty() : messages;
		updatedState = updatedState == null ? Mono.empty() : updatedState;
	}
}

