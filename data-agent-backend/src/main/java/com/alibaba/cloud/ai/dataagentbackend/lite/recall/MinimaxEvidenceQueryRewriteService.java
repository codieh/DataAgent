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
		return rewrite(query, null);
	}

	@Override
	public String rewrite(String query, String multiTurnContext) {
		String original = query == null ? "" : query.trim();
		if (original.isBlank()) {
			return original;
		}
		String system = """
				你是一位专业的搜索查询重写专家，位于数据分析工作流的知识召回环节。
				你的任务是将用户输入重写为一个独立、完整、无歧义的陈述句，以便后续进行向量库语义检索。
				只输出改写后的查询文本，不要输出 JSON、markdown、解释或任何额外内容。
				""".trim();

		String contextBlock = (multiTurnContext == null || multiTurnContext.isBlank()) ? "(无)"
				: multiTurnContext.trim();

		String user = """
				请将用户的最新输入重写为一个独立、完整、无歧义的检索查询。

				改写规则：
				1. 指代消解：如果用户使用了"它"、"这个"、"那边的"、"他们"等代词，必须根据多轮对话历史将其还原为具体的名词。
				   例子："那个的销量如何" -> "A产品的销量如何"
				2. 上下文补全：如果用户进行了简短追问（省略了主语或谓语），必须补全上下文信息。
				   例子："那华北呢？" -> "查询华北地区的销售额"
				3. 去噪与精简：去除礼貌用语（"你好"、"请问"、"麻烦帮我"）、情绪助词以及与查询意图无关的废话，保留核心业务实体、时间描述和指标名称。
				4. 保持语义不变：不要添加用户未提及的新需求，不要改变查询的核心意图。
				5. 如果最新输入开启了全新话题（与历史无关），则忽略历史，直接去噪重写。

				【多轮对话历史】
				%s

				<最新>用户输入：
				%s

				改写后的检索查询：
				""".formatted(contextBlock, original).trim();

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
