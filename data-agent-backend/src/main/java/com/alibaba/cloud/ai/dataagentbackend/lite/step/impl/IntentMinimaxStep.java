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
				你是数据分析 Agent 最前置的轻量意图分类器。
				你的唯一任务是判断“最新用户输入”应该被放行到后续数据分析链路，还是应当作为闲聊拦截。

				遵循极端保守原则：宁放过，不杀错。
				只要用户输入哪怕只有一丝可能是在查询、筛选、统计、比较、分析业务数据，就必须判为 DATA_ANALYSIS。
				只有在输入明确、毫无歧义地属于闲聊、礼貌寒暄、元问题或完全无关内容时，才判为 CHITCHAT。

				你必须只返回合法 JSON，不要输出 markdown、解释文本或代码块。
				""".trim();

		String user = buildIntentPrompt(resolveMultiTurnContext(state), state.getQuery());

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
			IntentResult parsed = objectMapper.readValue(json, IntentResult.class);
			return new IntentResult(normalizeClassification(parsed.classification()), parsed.reason());
		}
		catch (Exception e) {
			return new IntentResult("DATA_ANALYSIS", "parse failed: " + e.getMessage());
		}
	}

	static String buildIntentPrompt(String multiTurnContext, String query) {
		String multiTurn = multiTurnContext == null || multiTurnContext.isBlank() ? "(无)" : multiTurnContext.trim();
		String latestQuery = query == null ? "" : query.trim();
		return """
				请将最新用户输入分类为以下两类之一：
				- DATA_ANALYSIS：可能需要查询、筛选、统计、比较、分析、解释业务数据，或是对上一轮数据问题的追问/补充
				- CHITCHAT：明确的闲聊、寒暄、感谢、无关常识问题、关于 AI 自身的元问题、无意义乱码

				分类规则：
				1. 只要输入与业务实体、指标、报表、查询动作、排序、时间范围、筛选条件、多轮追问有关，一律判为 DATA_ANALYSIS。
				2. 多轮对话中，出现“这些/他们/那个/继续/改成/换成/再看一下/具体一点”等承接上文的表达时，只要上文涉及数据分析，一律判为 DATA_ANALYSIS。
				3. 即使表达口语化、信息不完整、缺少分析关键词，只要可能是在问业务数据，也判为 DATA_ANALYSIS。
				4. 只有当输入明确与业务数据无关时，才判为 CHITCHAT。

				少量示例：
				- 最新输入：你好呀 -> CHITCHAT
				- 最新输入：你是谁 -> CHITCHAT
				- 最新输入：给我看看销售部 -> DATA_ANALYSIS
				- 最新输入：前10个里面最便宜的是谁 -> DATA_ANALYSIS
				- 最新输入：他们呢？（若上文在查数据）-> DATA_ANALYSIS

				输出格式：
				{"classification":"DATA_ANALYSIS|CHITCHAT","reason":"一句简短原因"}

				【多轮输入】
				%s

				<最新>用户输入：
				%s
				""".formatted(multiTurn, latestQuery).trim();
	}

	static String normalizeClassification(String rawClassification) {
		if (rawClassification == null || rawClassification.isBlank()) {
			return "DATA_ANALYSIS";
		}
		String normalized = rawClassification.trim().toUpperCase();
		if (normalized.contains("CHITCHAT") || rawClassification.contains("闲聊") || rawClassification.contains("无关")) {
			return "CHITCHAT";
		}
		if (normalized.contains("DATA_ANALYSIS") || rawClassification.contains("数据分析") || rawClassification.contains("可能的数据分析请求")) {
			return "DATA_ANALYSIS";
		}
		return "DATA_ANALYSIS";
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

	private static String resolveMultiTurnContext(SearchLiteState state) {
		String multiTurn = state == null ? "" : state.getMultiTurnContext();
		return multiTurn == null || multiTurn.isBlank() ? "(无)" : multiTurn.trim();
	}

}
