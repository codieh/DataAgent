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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * 查询增强（Enhance）阶段：用 LLM 将用户原始问题规范化为 canonicalQuery，并生成少量 expandedQueries。
 *
 * <p>
 * 目的：
 * <ul>
 *   <li>把“口语化/省略/指代”的问题，改写成更适合 SQL 生成的一句明确问题（canonicalQuery）；</li>
 *   <li>生成 1~3 条等价改写或补全版本（expandedQueries），用于后续可选的多路检索/多候选 SQL。</li>
 * </ul>
 * </p>
 *
 * <p>
 * 输出约定：模型必须返回 JSON，不要带 markdown。
 * </p>
 */
@Component
@Order(35)
@ConditionalOnProperty(name = "search.lite.enhance.provider", havingValue = "minimax")
public class EnhanceMinimaxStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(EnhanceMinimaxStep.class);

	private final AnthropicClient anthropicClient;

	private final ObjectMapper objectMapper;

	public EnhanceMinimaxStep(AnthropicClient anthropicClient, ObjectMapper objectMapper) {
		this.anthropicClient = Objects.requireNonNull(anthropicClient, "anthropicClient");
		this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.ENHANCE;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		String currentTime = java.time.LocalDateTime.now().format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));

		String system = """
				你是一位顶级的自然语言理解专家，擅长融合业务知识，对用户查询进行澄清、转换、扩展。
				你必须只返回合法 JSON，不要输出 markdown、解释文本或代码块。
				""".trim();

		String user = """
				请处理用户查询，输出以下两个字段：
				- canonicalQuery：一个清晰、完整、独立的规范化查询，可直接用于 SQL 生成
				- expandedQueries：1-3 个语义相同但表达不同的扩展查询（canonicalQuery 作为第一项）

				处理规则：
				1. 查询澄清：结合多轮对话历史，理解用户完整意图，进行指代消解（"它"->"A产品"）。
				2. 时间转换：识别相对时间（"最近7天"、"上个月"），根据当前时间转换为绝对日期或范围。
				3. 业务术语解析：查阅业务知识，将查询中的业务术语替换为其具体的、可用数据描述的定义。
				4. 保持语义不变：不要编造新的业务需求，不要添加用户未提及的约束。
				5. 如果查询已经清晰，canonicalQuery 可以等于原查询。

				输出 JSON 格式：
				{"canonicalQuery":"...","expandedQueries":["...","..."]}

				---

				示例：
				[当前时间: 2025-11-08 11:11:12]
				【业务知识】: "核心用户"被定义为最近30天内消费总额超过5000元的用户。
				【多轮输入】: (无)
				<最新>用户输入: 帮我看看上个月的核心用户有多少
				输出：
				{"canonical_query":"查询上个月（2025-10-01至2025-10-31）期间，消费总额超过5000元的用户数量","expanded_queries":["统计在2025年10月份，累计消费金额大于5000的客户总数是多少？","找出上个月消费超过5000元的核心用户有多少人"]}

				---

				[当前时间: %s]

				【业务知识】:
				%s

				【文档定义】:
				%s

				【多轮输入】:
				%s

				<最新>用户输入:
				%s

				输出：
				""".formatted(currentTime, resolveEvidenceContext(state), resolveDocumentContext(state),
						resolveMultiTurnContext(state), state.getQuery()).trim();

		Flux<SearchLiteMessage> start = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在进行查询增强...", null))
			.delayElements(Duration.ofMillis(50));

		Flux<String> sharedDeltas = anthropicClient.streamMessage(system, user).cache();

		Flux<SearchLiteMessage> streaming = sharedDeltas
			.map(delta -> SearchLiteMessages.message(context, stage(), SearchLiteMessageType.JSON, delta, null));

		Mono<SearchLiteState> updated = sharedDeltas.collect(StringBuilder::new, StringBuilder::append).map(sb -> {
			EnhanceResult r = parseEnhanceResult(sb.toString(), state.getQuery());
			state.setCanonicalQuery(r.canonicalQuery());
			state.setExpandedQueries(r.expandedQueries());
			return state;
		}).doOnNext(s -> log.info("enhance done: threadId={}, canonicalLen={}, expanded={}", context.threadId(),
				s.getCanonicalQuery() == null ? 0 : s.getCanonicalQuery().length(),
				s.getExpandedQueries() == null ? 0 : s.getExpandedQueries().size()));

		Flux<SearchLiteMessage> done = updated.map(s -> SearchLiteMessages.message(context, stage(),
				SearchLiteMessageType.JSON, null,
				Map.of("canonicalQuery", s.getCanonicalQuery(), "expandedQueries", s.getExpandedQueries()))).flux();

		return new SearchLiteStepResult(start.concatWith(streaming).concatWith(done), updated);
	}

	private EnhanceResult parseEnhanceResult(String raw, String fallback) {
		if (raw == null) {
			return new EnhanceResult(fallback, List.of(fallback));
		}
		String trimmed = raw.trim();
		String json = extractJsonObject(trimmed);
		try {
			EnhanceResult r = objectMapper.readValue(json, EnhanceResult.class);
			String canonical = (r.canonicalQuery() == null || r.canonicalQuery().isBlank()) ? fallback
					: r.canonicalQuery().trim();
			List<String> expanded = (r.expandedQueries() == null || r.expandedQueries().isEmpty())
					? List.of(canonical)
					: r.expandedQueries().stream().filter(s -> s != null && !s.isBlank()).map(String::trim).toList();
			// 保证 expanded 的第一个是 canonical，并去重（避免 block）
			LinkedHashSet<String> ordered = new LinkedHashSet<>();
			ordered.add(canonical);
			ordered.addAll(expanded);
			List<String> normalizedExpanded = new ArrayList<>(ordered);
			return new EnhanceResult(canonical, normalizedExpanded);
		}
		catch (Exception e) {
			return new EnhanceResult(fallback, List.of(fallback));
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

	private static String resolveEvidenceContext(SearchLiteState state) {
		String evidence = state == null ? "" : state.getEvidenceText();
		return evidence == null || evidence.isBlank() ? "(无业务规则提示)" : evidence.trim();
	}

	private static String resolveDocumentContext(SearchLiteState state) {
		String documents = state == null ? "" : state.getDocumentText();
		return documents == null || documents.isBlank() ? "(无文档定义补充)" : documents.trim();
	}

	private static String resolveMultiTurnContext(SearchLiteState state) {
		String multiTurn = state == null ? "" : state.getMultiTurnContext();
		return multiTurn == null || multiTurn.isBlank() ? "(无)" : multiTurn.trim();
	}

	private record EnhanceResult(String canonicalQuery, List<String> expandedQueries) {
	}

}
