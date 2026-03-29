package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.llm.anthropic.AnthropicClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.util.Objects;

/**
 * 参考 management，在 evidence recall 前先把用户问题改写为更适合检索的 standalone query。
 */
@Component
@ConditionalOnProperty(name = "search.lite.evidence.rewrite.provider", havingValue = "minimax")
public class MinimaxEvidenceQueryRewriteService implements EvidenceQueryRewriteService {

	private static final Logger log = LoggerFactory.getLogger(MinimaxEvidenceQueryRewriteService.class);

	private final AnthropicClient anthropicClient;

	public MinimaxEvidenceQueryRewriteService(AnthropicClient anthropicClient) {
		this.anthropicClient = Objects.requireNonNull(anthropicClient, "anthropicClient");
	}

	@Override
	public String rewrite(String query) {
		String original = query == null ? "" : query.trim();
		if (original.isBlank()) {
			return original;
		}
		String system = """
				You rewrite user questions for evidence retrieval in a data analysis assistant.
				Return ONLY a single plain-text rewritten query.
				Do not output JSON, markdown, bullets, or explanations.
				""".trim();

		String user = """
				Rewrite the user question into one standalone retrieval query for business knowledge recall.

				Rules:
				- Keep the meaning unchanged.
				- Preserve business metrics, dimensions, filters, and time ranges.
				- Remove chatty wording and make the query retrieval-friendly.
				- Focus on business definitions, metric explanations, and domain rules.
				- Output a single sentence only.

				User question:
				%s
				""".formatted(original).trim();

		try {
			String rewritten = anthropicClient.createMessage(system, user).block();
			String normalized = normalize(rewritten, original);
			log.info("evidence rewrite done: originalLen={}, rewrittenLen={}", original.length(), normalized.length());
			return normalized;
		}
		catch (Exception e) {
			log.warn("evidence rewrite failed, fallback original query: error={}", e.getMessage());
			return original;
		}
	}

	private String normalize(String rewritten, String fallback) {
		if (rewritten == null || rewritten.isBlank()) {
			return fallback;
		}
		String normalized = rewritten.replace("```", "").trim();
		return normalized.isBlank() ? fallback : normalized;
	}

}
