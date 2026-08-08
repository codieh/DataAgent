package com.alibaba.cloud.ai.dataagentbackend.lite.llm;

import com.alibaba.cloud.ai.dataagentbackend.llm.anthropic.AnthropicClient;
import java.util.Objects;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * 统一的 LLM 调用门面。
 * <p>
 * 约定：
 * <ul>
 *   <li>业务节点优先使用 {@link #completeAsync(String, String)} / {@link #streamAsync(String, String)}；</li>
 *   <li>只有同步边界层（例如 graph 的同步 node、同步接口适配层）才允许调用 {@link #awaitAtBoundary(Mono, String)}；</li>
 *   <li>禁止在业务节点中直接对 {@link Mono}/{@link Flux} 调用 {@code block()}。</li>
 * </ul>
 */
@Component
public class SearchLiteLlmGateway {

	private final AnthropicClient anthropicClient;

	public SearchLiteLlmGateway(AnthropicClient anthropicClient) {
		this.anthropicClient = Objects.requireNonNull(anthropicClient, "anthropicClient");
	}

	public Mono<String> completeAsync(String systemPrompt, String userPrompt) {
		return anthropicClient.createMessage(systemPrompt, userPrompt);
	}

	public Flux<String> streamAsync(String systemPrompt, String userPrompt) {
		return anthropicClient.streamMessage(systemPrompt, userPrompt);
	}

	public String awaitAtBoundary(Mono<String> result, String fallback) {
		try {
			return result.blockOptional().orElse(fallback);
		}
		catch (Exception ignored) {
			return fallback;
		}
	}

}
