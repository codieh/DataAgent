package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLitePlanStep;
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
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * 结果总结阶段：基于 SQL 与结果集生成自然语言总结（真流式）。
 *
 * <p>
 * 说明：这是精简版实现，主要用于提升演示效果；生产场景可加入指标提取/异常检测/可视化建议等。
 * </p>
 */
@Component
@Order(60)
@ConditionalOnProperty(name = "search.lite.result.provider", havingValue = "minimax")
public class ResultMinimaxStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(ResultMinimaxStep.class);

	private final SearchLiteLlmGateway llmGateway;

	private final ObjectMapper objectMapper;

	private final int maxRowsForPrompt;

	public ResultMinimaxStep(SearchLiteLlmGateway llmGateway, ObjectMapper objectMapper,
			@Value("${search.lite.result.max-rows-for-prompt:20}") int maxRowsForPrompt) {
		this.llmGateway = Objects.requireNonNull(llmGateway, "llmGateway");
		this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
		this.maxRowsForPrompt = Math.max(1, maxRowsForPrompt);
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.RESULT;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		SearchLiteStepResult predefinedResult = handlePredefinedResultMode(context, state);
		if (predefinedResult != null) {
			return predefinedResult;
		}

		// 如果前面已经有错误，直接收尾输出（避免再请求 LLM）
		if (StringUtils.hasText(state.getError())) {
			String summary = "执行失败：" + state.getError();
			state.setResultSummary(summary);
			Flux<SearchLiteMessage> messages = Flux.just(
					SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在整理结果...", null),
					SearchLiteMessages.done(context, stage(), SearchLiteMessageType.JSON, null,
							Map.of("summary", summary, "ok", false)))
				.delayElements(Duration.ofMillis(80));
			return new SearchLiteStepResult(messages, Mono.just(state));
		}

		String sql = state.getSql();
		List<Map<String, Object>> rows = state.getRows();
		int rowCount = rows == null ? 0 : rows.size();
		List<Map<String, Object>> preview = rows == null ? List.of() : rows.stream().limit(maxRowsForPrompt).toList();

		String system = """
				你是一位专业的数据分析顾问，需要基于 SQL 执行结果，生成简洁、准确的中文总结。
				根据提供的数据结果进行推理，不得杜撰数据。
				""".trim();

		String user = buildUserPrompt(state, sql, rowCount, preview);

		log.info("result-summary start: threadId={}, sqlLen={}, rows={}, previewRows={}", context.threadId(),
				sql == null ? 0 : sql.length(), rowCount, preview.size());

		Flux<SearchLiteMessage> start = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在整理结果...", null))
			.delayElements(Duration.ofMillis(50));

		Flux<String> sharedDeltas = llmGateway.streamAsync(system, user).cache();

		Flux<SearchLiteMessage> streaming = sharedDeltas
			.map(delta -> SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, delta, null));

		Mono<SearchLiteState> updated = sharedDeltas.collect(StringBuilder::new, StringBuilder::append).map(sb -> {
			String summary = sb.toString().trim();
			state.setResultSummary(summary);
			return state;
		});

		Flux<SearchLiteMessage> done = updated.map(s -> {
			Map<String, Object> payload = new LinkedHashMap<>();
			payload.put("ok", true);
			payload.put("summary", s.getResultSummary());
			payload.put("rowCount", rowCount);
			if (state.isPlannerEnabled()) {
				payload.put("planSummary", buildPlanSummaryPayload(state));
			}
			return SearchLiteMessages.done(context, stage(), SearchLiteMessageType.JSON, null, payload);
		}).flux();

		return new SearchLiteStepResult(start.concatWith(streaming).concatWith(done), updated);
	}

	private SearchLiteStepResult handlePredefinedResultMode(SearchLiteContext context, SearchLiteState state) {
		String mode = safe(state.getResultMode());
		if (!StringUtils.hasText(mode) || "success".equalsIgnoreCase(mode)) {
			return null;
		}
		String summary = switch (mode) {
			case "no_schema" -> "未找到与当前问题相关的数据表，请补充更明确的业务对象、指标名称或筛选条件后再试。";
			case "no_sql" -> "当前问题暂未生成可执行 SQL，请换一种更明确的描述，或拆分问题后重试。";
			case "execution_error" -> "执行失败：" + safe(state.getError());
			case "waiting_human_feedback" -> "计划已生成，等待人工审核。请基于当前 threadId 提交审核结果后继续执行。";
			case "blocked_sensitive_sql" -> "当前查询涉及敏感字段或敏感明细，已被安全策略拦截。建议改为统计类查询或去除敏感字段后重试。";
			case "blocked_wide_export" -> "当前查询可能导致大范围明细导出，已被安全策略拦截。建议增加筛选条件、限制范围，或改为聚合统计后重试。";
			case "need_clarification" -> StringUtils.hasText(state.getFeasibilityMessage())
					? state.getFeasibilityMessage()
					: "当前问题信息不足，无法生成准确查询。请补充更明确的业务对象、指标名称或筛选条件后再试。";
			case "free_chat" -> StringUtils.hasText(state.getFeasibilityMessage())
					? state.getFeasibilityMessage()
					: "当前请求不是数据分析类问题，无法通过数据查询回答。请问您是否有数据分析相关的需求？";
			default -> null;
		};
		if (!StringUtils.hasText(summary)) {
			return null;
		}
		if (state.isPlannerEnabled()) {
			summary = buildPlannerAwarePredefinedSummary(state, summary);
		}
		state.setResultSummary(summary);
		boolean ok = "success".equalsIgnoreCase(mode);
		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("summary", summary);
		payload.put("ok", ok);
		payload.put("resultMode", mode);
		if (state.isPlannerEnabled()) {
			payload.put("planSummary", buildPlanSummaryPayload(state));
		}
		Flux<SearchLiteMessage> messages = Flux.just(
				SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在整理结果...", null),
				SearchLiteMessages.done(context, stage(), SearchLiteMessageType.JSON, null, payload))
			.delayElements(Duration.ofMillis(80));
		return new SearchLiteStepResult(messages, Mono.just(state));
	}

	private String buildUserPrompt(SearchLiteState state, String sql, int rowCount, List<Map<String, Object>> preview) {
		String query = state.getQuery();
		String rowsJson;
		try {
			rowsJson = objectMapper.writeValueAsString(preview);
		}
		catch (Exception e) {
			rowsJson = String.valueOf(preview);
		}
		return """
				# 用户问题
				%s

				# 执行计划与完成步骤
				%s

				# 执行的 SQL
				%s

				# 返回行数
				%d

				# 数据预览（JSON）
				%s

				# 计划步骤总结
				%s

				# 输出要求
				1. 提供 3-6 条要点总结。
				2. 提及返回行数和明显的规律或趋势。
				3. 如果有多个计划步骤，综合所有步骤进行总结，不要只看最后一条 SQL。
				4. 明确说明计划了多少步骤、哪些成功/失败、每步发现了什么。
				5. 如果结果为空，解释可能原因并建议后续查询。
				6. 只基于提供的数据进行总结，不要补充你认为应该有的数据。
				""".formatted(safe(query), planJson(state), safe(sql), rowCount, rowsJson, planSummaryText(state)).trim();
	}

	private String planJson(SearchLiteState state) {
		List<SearchLitePlanStep> steps = state.getPlanSteps();
		if (steps == null || steps.isEmpty()) {
			return "(无多步骤计划)";
		}
		try {
			return objectMapper.writeValueAsString(steps);
		}
		catch (Exception e) {
			return String.valueOf(steps);
		}
	}

	private String planSummaryText(SearchLiteState state) {
		List<SearchLitePlanStep> steps = state.getPlanSteps();
		if (!state.isPlannerEnabled() || steps == null || steps.isEmpty()) {
			return "(单步执行)";
		}
		StringBuilder builder = new StringBuilder();
		builder.append("Total steps: ").append(steps.size()).append('\n');
		for (SearchLitePlanStep step : steps) {
			if (step == null) {
				continue;
			}
			builder.append("- Step ").append(step.getStep()).append(" [").append(safe(step.getStatus())).append("] ")
				.append(safe(step.getInstruction())).append('\n');
			builder.append("  Row count: ").append(step.getRowCount()).append('\n');
			if (StringUtils.hasText(step.getSummarySnippet())) {
				builder.append("  Summary: ").append(step.getSummarySnippet()).append('\n');
			}
			if (StringUtils.hasText(step.getError())) {
				builder.append("  Error: ").append(step.getError()).append('\n');
			}
		}
		return builder.toString().trim();
	}

	private Map<String, Object> buildPlanSummaryPayload(SearchLiteState state) {
		List<SearchLitePlanStep> steps = state.getPlanSteps();
		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("plannerEnabled", state.isPlannerEnabled());
		payload.put("planFinishedReason", safe(state.getPlanFinishedReason()));
		payload.put("totalSteps", steps == null ? 0 : steps.size());
		payload.put("steps", steps == null ? List.of() : steps);
		return payload;
	}

	private String buildPlannerAwarePredefinedSummary(SearchLiteState state, String fallbackSummary) {
		List<SearchLitePlanStep> steps = state.getPlanSteps();
		if (steps == null || steps.isEmpty()) {
			return fallbackSummary;
		}
		return """
				%s

				计划执行概览：
				%s
				""".formatted(fallbackSummary, planSummaryText(state)).trim();
	}

	private static String safe(String s) {
		return s == null ? "" : s.trim();
	}

}
