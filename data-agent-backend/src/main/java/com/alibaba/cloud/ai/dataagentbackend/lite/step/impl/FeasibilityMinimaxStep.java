package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.llm.SearchLiteLlmGateway;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.Map;
import java.util.Objects;

/**
 * 可行性评估阶段：在查询增强之后、SQL 生成之前，判断用户请求是否可被当前 Schema + 证据回答。
 *
 * <p>
 * 三种结果：
 * <ul>
 *   <li>数据分析 - 继续后续流程</li>
 *   <li>需要澄清 - 跳转到结果阶段，提示用户补充信息</li>
 *   <li>自由闲聊 - 跳转到结果阶段，礼貌拒绝</li>
 * </ul>
 * </p>
 */
@Component
@Order(37)
public class FeasibilityMinimaxStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(FeasibilityMinimaxStep.class);

	private final SearchLiteLlmGateway llmGateway;

	private final ObjectMapper objectMapper;

	private final boolean enabled;

	public FeasibilityMinimaxStep(SearchLiteLlmGateway llmGateway, ObjectMapper objectMapper,
			@Value("${search.lite.feasibility.enabled:false}") boolean enabled) {
		this.llmGateway = Objects.requireNonNull(llmGateway, "llmGateway");
		this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
		this.enabled = enabled;
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.FEASIBILITY;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		if (!enabled) {
			state.setFeasibilityResult("数据分析");
			state.setFeasibilityMessage("");
			Flux<SearchLiteMessage> msg = Flux.just(SearchLiteMessages.message(context, stage(),
					SearchLiteMessageType.TEXT, "已跳过可行性评估，继续后续流程。", null));
			return new SearchLiteStepResult(msg, Mono.just(state));
		}
		// 如果不是数据分析意图，跳过可行性评估
		if (!"DATA_ANALYSIS".equalsIgnoreCase(safe(state.getIntentClassification()))) {
			state.setFeasibilityResult("自由闲聊");
			state.setFeasibilityMessage("当前请求不是数据分析类问题，无法通过数据查询回答。");
			state.setResultMode("free_chat");
			Flux<SearchLiteMessage> msg = Flux
				.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "当前请求不是数据分析问题，跳过后续流程。", null))
				.delayElements(Duration.ofMillis(50));
			return new SearchLiteStepResult(msg, Mono.just(state));
		}

		String system = """
				你是一名经验丰富且务实的数据分析专家。你的任务是结合用户的查询、相关的业务知识以及数据库结构，判断用户的请求是否有可能被回答，并决定是直接分析，还是需要澄清关键点。
				你必须只返回合法 JSON，不要输出 markdown、解释文本或代码块。
				""".trim();

		String user = buildFeasibilityPrompt(state);

		log.info("feasibility start: threadId={}, queryLen={}, schemaLen={}, evidenceLen={}", context.threadId(),
				state.getEffectiveQuery() == null ? 0 : state.getEffectiveQuery().length(),
				state.getRecalledSchemaText() == null ? 0 : state.getRecalledSchemaText().length(),
				state.getEvidenceText() == null ? 0 : state.getEvidenceText().length());

		Flux<SearchLiteMessage> start = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在评估查询可行性...", null))
			.delayElements(Duration.ofMillis(50));

		Flux<String> sharedDeltas = llmGateway.streamAsync(system, user).cache();

		Flux<SearchLiteMessage> streaming = sharedDeltas
			.map(delta -> SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, delta, null));

		Mono<SearchLiteState> updated = sharedDeltas.collect(StringBuilder::new, StringBuilder::append).map(sb -> {
			FeasibilityResult r = parseFeasibilityResult(sb.toString());
			state.setFeasibilityResult(r.result());
			state.setFeasibilityMessage(r.message());

			if ("需要澄清".equals(r.result())) {
				state.setResultMode("need_clarification");
			} else if ("自由闲聊".equals(r.result())) {
				state.setResultMode("free_chat");
			}
			return state;
		}).doOnNext(s -> log.info("feasibility done: threadId={}, result={}, messageLen={}", context.threadId(),
				s.getFeasibilityResult(), s.getFeasibilityMessage() == null ? 0 : s.getFeasibilityMessage().length()));

		Flux<SearchLiteMessage> done = updated.map(s -> SearchLiteMessages.message(context, stage(),
				SearchLiteMessageType.JSON, null,
				Map.of("feasibilityResult", safe(s.getFeasibilityResult()), "feasibilityMessage", safe(s.getFeasibilityMessage())))).flux();

		return new SearchLiteStepResult(start.concatWith(streaming).concatWith(done), updated);
	}

	private String buildFeasibilityPrompt(SearchLiteState state) {
		return """
				# 核心原则
				你的判断应倾向于乐观和包容。只要用户的核心意图能在召回的数据库Schema和业务参考信息中找到相关线索，就应该优先尝试数据分析。只在遇到无法绕过的关键信息缺失时，才请求澄清。

				# 任务与决策逻辑

				1. 综合分析可行性：
				   - 检查【规范化查询】中的核心概念是否能在【召回的数据库Schema】中直接找到对应字段。
				   - 如果找不到直接对应，查阅【参考信息】，看是否有业务规则能将用户的术语映射到Schema中的字段和条件。
				   - 只要通过Schema和Evidence能覆盖查询的核心要求，就认为是可行的。

				2. 确定需求类型：
				   - 数据分析：绝大多数关键信息能通过直接映射Schema或借助Evidence解释后找到合理的对应。
				   - 需要澄清：核心实体或指标在Schema和Evidence中都找不到任何解释或对应；或决定性概念模糊且Evidence未定义。
				   - 自由闲聊：召回的数据库Schema为空，且查询与业务无关。

				# 输出 JSON 格式
				{"result":"数据分析","message":""}
				或
				{"result":"需要澄清","message":"简明扼要的反问"}
				或
				{"result":"自由闲聊","message":"礼貌告知无法回答"}

				---

				# 示例1: 借助Evidence成功解析 -> 数据分析
				【规范化查询】: 查询所有"核心用户"的数量
				【召回的数据库Schema】:
				# 表名: user, 包含字段: [(user_id), (name), (registration_date)]
				# 表名: orders, 包含字段: [(order_id), (user_id), (order_amount), (order_date)]
				【参考信息】: "核心用户"被定义为最近30天内消费总额超过5000元的用户。

				输出: {"result":"数据分析","message":""}

				## 示例2: 核心指标完全缺失 -> 需要澄清
				【规范化查询】: 统计所有部门的总毛利是多少
				【召回的数据库Schema】:
				# 表名: 部门信息, 包含字段: [(部门编号), (部门名称), (员工人数)]
				【参考信息】: (无相关信息)

				输出: {"result":"需要澄清","message":"抱歉，我没有找到关于"毛利"的数据或计算方式。我这里有部门的"员工人数"等信息，请问您还需要查询其他内容吗？"}

				---

				# 正式任务

				【规范化查询】
				%s

				【召回的数据库Schema】
				%s

				【参考信息】
				%s

				【文档定义】
				%s

				【多轮输入】
				%s

				输出：
				""".formatted(safe(state.getEffectiveQuery()), safeOrDefault(state.getRecalledSchemaText(), "(无)"),
					safeOrDefault(state.getEvidenceText(), "(无)"), safeOrDefault(state.getDocumentText(), "(无)"),
					safeOrDefault(state.getMultiTurnContext(), "(无)")).trim();
	}

	private FeasibilityResult parseFeasibilityResult(String raw) {
		if (!StringUtils.hasText(raw)) {
			return new FeasibilityResult("数据分析", "");
		}
		String trimmed = raw.trim();
		String json = extractJsonObject(trimmed);
		try {
			FeasibilityResult r = objectMapper.readValue(json, FeasibilityResult.class);
			String result = safe(r.result());
			if (!"数据分析".equals(result) && !"需要澄清".equals(result) && !"自由闲聊".equals(result)) {
				return new FeasibilityResult("数据分析", "");
			}
			return new FeasibilityResult(result, safe(r.message()));
		}
		catch (Exception e) {
			log.warn("feasibility output parse failed, default to 数据分析: {}", e.getMessage());
			return new FeasibilityResult("数据分析", "");
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

	private static String safe(String s) {
		return s == null ? "" : s.trim();
	}

	private static String safeOrDefault(String value, String fallback) {
		return StringUtils.hasText(value) ? value.trim() : fallback;
	}

	private record FeasibilityResult(String result, String message) {
	}

}
