package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.alibaba.cloud.ai.dataagentbackend.llm.anthropic.AnthropicClient;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * 意图识别（Intent）阶段：使用 MiniMax 的 Anthropic 兼容接口进行分类，并把模型输出以“真流式”形式转发给前端。
 * <p>
 * 行为：
 * <ul>
 *   <li>模型输出增量（delta）到达时立即通过 SSE 发送给前端；</li>
 *   <li>同时将所有 delta 拼接为完整文本，最终解析出 JSON 中的 {@code classification} 写入 {@link SearchLiteState}。</li>
 * </ul>
 */
@Component
@Order(10)
@ConditionalOnProperty(name = "search.lite.intent.provider", havingValue = "minimax")
public class IntentMinimaxStep implements SearchLiteStep {

	private final AnthropicClient anthropicClient;

	private final ObjectMapper objectMapper;

	public IntentMinimaxStep(AnthropicClient anthropicClient, ObjectMapper objectMapper) {
		this.anthropicClient = anthropicClient;
		this.objectMapper = objectMapper;
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.INTENT;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		String system = """
				You are an intent classifier for a data analysis assistant.
				Return ONLY valid JSON without markdown or extra text.
				""".trim();

		String user = """
				Classify the user query into one of:
				- DATA_ANALYSIS: requires SQL/data retrieval/analysis
				- CHITCHAT: casual chat or unrelated

				Output JSON schema:
				{"classification":"DATA_ANALYSIS|CHITCHAT","reason":"short reason"}

				User query:
				%s
				""".formatted(state.getQuery()).trim();

		Flux<SearchLiteMessage> start = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在进行意图识别...", null))
			.delayElements(Duration.ofMillis(50));

		// 这条 delta 流会被消费两次：
		// 1) streaming：实时转发给前端；2) updated：拼接并解析最终 JSON。
		// cache() 用于避免“二次订阅导致二次 HTTP 请求”。
		Flux<String> sharedDeltas = anthropicClient.streamMessage(system, user).cache();

		Flux<SearchLiteMessage> streaming = sharedDeltas
			.map(delta -> SearchLiteMessages.message(context, stage(), SearchLiteMessageType.JSON, delta, null));

		Mono<SearchLiteState> updated = sharedDeltas.collect(StringBuilder::new, StringBuilder::append).map(sb -> {
			IntentResult result = parseIntentResult(sb.toString());
			state.setIntentClassification(result.classification());
			return state;
		});

		Flux<SearchLiteMessage> done = updated.map(s -> SearchLiteMessages.message(context, stage(),
				SearchLiteMessageType.JSON, null, Map.of("classification", s.getIntentClassification()))).flux();

		return new SearchLiteStepResult(start.concatWith(streaming).concatWith(done), updated);
	}

	private IntentResult parseIntentResult(String raw) {
		if (raw == null) {
			return new IntentResult("DATA_ANALYSIS", "empty response");
		}
		String trimmed = raw.trim();
		String json = extractJsonObject(trimmed);
		try {
			return objectMapper.readValue(json, IntentResult.class);
		}
		catch (Exception e) {
			return new IntentResult("DATA_ANALYSIS", "parse failed: " + e.getMessage());
		}
	}

	private static String extractJsonObject(String text) {
		int start = text.indexOf('{');
		int end = text.lastIndexOf('}');
		if (start >= 0 && end > start) {
			return text.substring(start, end + 1);
		}
		return text;
	}

	private record IntentResult(String classification, String reason) {
	}

}
