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
		String system = """
				You rewrite user queries for a SQL data assistant.
				Return ONLY valid JSON without markdown or extra text.
				""".trim();

		String user = """
				Given the user query, output:
				- canonicalQuery: a single clear and complete question for SQL generation
				- expandedQueries: 1-3 alternative rewrites (including the canonicalQuery as the first item)

				Rules:
				- Keep the meaning the same; do NOT invent new business requirements.
				- Preserve time ranges and filters if present.
				- You may use business rules and document definitions to clarify domain terms, but do NOT add unrelated constraints.
				- If the query is already clear, canonicalQuery can equal the original query.

				Output JSON schema:
				{"canonicalQuery":"...","expandedQueries":["...","..."]}

				Business rules / FAQ hints:
				%s

				Definition / background documents:
				%s

				User query:
				%s
				""".formatted(resolveEvidenceContext(state), resolveDocumentContext(state), state.getQuery()).trim();

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

	private record EnhanceResult(String canonicalQuery, List<String> expandedQueries) {
	}

}
