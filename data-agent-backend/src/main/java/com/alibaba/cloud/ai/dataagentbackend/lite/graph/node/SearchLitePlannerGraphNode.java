package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLitePlanStep;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageEmitter;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateMapper;
import com.alibaba.cloud.ai.dataagentbackend.lite.trace.SearchLiteTraceRecorder;
import com.alibaba.cloud.ai.dataagentbackend.llm.anthropic.AnthropicClient;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

@Component
public class SearchLitePlannerGraphNode implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLitePlannerGraphNode.class);

	private final AnthropicClient anthropicClient;

	private final ObjectMapper objectMapper;

	private final SearchLiteGraphMessageEmitter messageEmitter;

	private final SearchLiteTraceRecorder traceRecorder;

	private final int maxSteps;

	public SearchLitePlannerGraphNode(AnthropicClient anthropicClient, ObjectMapper objectMapper,
			SearchLiteGraphMessageEmitter messageEmitter, SearchLiteTraceRecorder traceRecorder,
			@Value("${search.lite.graph.planner.max-steps:5}") int maxSteps) {
		this.anthropicClient = Objects.requireNonNull(anthropicClient, "anthropicClient");
		this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
		this.messageEmitter = Objects.requireNonNull(messageEmitter, "messageEmitter");
		this.traceRecorder = Objects.requireNonNull(traceRecorder, "traceRecorder");
		this.maxSteps = Math.max(1, maxSteps);
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		SearchLiteState liteState = SearchLiteGraphStateMapper.toSearchLiteState(state);
		SearchLiteState beforeState = SearchLiteGraphStateMapper.toSearchLiteState(state);
		SearchLiteContext context = new SearchLiteContext(resolveThreadId(liteState));
		long startedAt = System.nanoTime();
		if (shouldReuseApprovedPlan(liteState)) {
			liteState.setHumanFeedbackStatus(null);
			liteState.setHumanFeedbackComment(null);
			liteState.setAwaitingHumanFeedback(false);
			liteState.setPlannerDecision("proceed");
			liteState.setPlannerDecisionReason("");
			messageEmitter.emitOne(context.threadId(), SearchLiteMessages.done(context, SearchLiteStage.PLANNER,
					SearchLiteMessageType.JSON, null,
					Map.of("decision", liteState.getPlannerDecision(), "reason", safe(liteState.getPlannerDecisionReason()),
							"steps", liteState.getPlanSteps(), "plannerEnabled", liteState.isPlannerEnabled(),
							"rawPlanLen", liteState.getPlannerRawOutput() == null ? 0 : liteState.getPlannerRawOutput().length(),
							"reusedApprovedPlan", true)));
			traceRecorder.recordStage(context.threadId(), SearchLiteStage.PLANNER, "reuse-approved-plan",
					(System.nanoTime() - startedAt) / 1_000_000, beforeState, liteState, null);
			log.info("graph planner node reused approved plan: steps={}", liteState.getPlanSteps().size());
			return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
		}
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.message(context, SearchLiteStage.PLANNER,
				SearchLiteMessageType.TEXT, "正在规划分析步骤...", null));

		String system = """
				你是一位拥有深厚业务洞察力的高级数据分析专家。
				你的任务是基于给定的数据库 Schema、业务知识和文档定义，先判断当前请求是否可以继续执行，再在可执行时制定一个严谨的 SQL 执行计划。
				你必须且只能输出一个合法 JSON 对象，严禁包含 markdown、注释或 JSON 结构之外的任何文本。
				""".trim();
		String user = buildPlannerPrompt(liteState);
		String rawOutput;
		try {
			rawOutput = anthropicClient.createMessage(system, user).blockOptional().orElse("");
		}
		catch (Exception ex) {
			rawOutput = "";
			log.warn("planner llm generation failed: threadId={}, error={}", context.threadId(), ex.getMessage());
		}

		PlannerOutput plannerOutput = parsePlannerOutput(rawOutput, liteState);
		liteState.setPlanSteps(plannerOutput.steps());
		liteState.setCurrentPlanStepIndex(0);
		liteState.setPlannerEnabled(plannerOutput.steps().size() > 1);
		liteState.setPlannerDecision(plannerOutput.decision());
		liteState.setPlannerDecisionReason(plannerOutput.reason());
		liteState.setPlanFinished(false);
		liteState.setPlanFinishedReason(null);
		liteState.setPlannerRawOutput(rawOutput);
		liteState.setPlanValidationStatus(true);
		liteState.setPlanValidationError(null);
		liteState.setHumanFeedbackStatus(null);
		liteState.setHumanFeedbackComment(null);
		liteState.setAwaitingHumanFeedback(false);

		applyPlannerDecision(plannerOutput, liteState);

		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.done(context, SearchLiteStage.PLANNER,
				SearchLiteMessageType.JSON, null,
				Map.of("decision", liteState.getPlannerDecision(), "reason", safe(liteState.getPlannerDecisionReason()),
						"steps", plannerOutput.steps(), "plannerEnabled", liteState.isPlannerEnabled(),
						"rawPlanLen", rawOutput == null ? 0 : rawOutput.length())));
		traceRecorder.recordStage(context.threadId(), SearchLiteStage.PLANNER, "generate-plan",
				(System.nanoTime() - startedAt) / 1_000_000, beforeState, liteState, null);
		log.info("graph planner node invoked: decision={}, steps={}, plannerEnabled={}, repairCount={}, stepInstructions={}",
				liteState.getPlannerDecision(), plannerOutput.steps().size(), liteState.isPlannerEnabled(),
				liteState.getPlanRepairCount(),
				plannerOutput.steps().stream().map(SearchLitePlanStep::getInstruction).toList());
		return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
	}

	private boolean shouldReuseApprovedPlan(SearchLiteState state) {
		return "APPROVED".equalsIgnoreCase(safe(state.getHumanFeedbackStatus())) && state.getPlanSteps() != null
				&& !state.getPlanSteps().isEmpty() && state.isPlanValidationStatus();
	}

	private String buildPlannerPrompt(SearchLiteState state) {
		StringBuilder prompt = new StringBuilder("""
				# 核心任务
				为当前数据分析请求创建一个 SQL 执行计划。

				# 输出 JSON 格式
				{
				  "decision": "proceed",
				  "reason": "",
				  "tables": ["orders"],
				  "columns": ["orders.status"],
				  "steps": [
				    {
				      "step": 1,
				      "instruction": "...",
				      "tool": "SQL"
				    }
				  ]
				}

				# 规则
				1. 只使用 "SQL" 作为 tool 值。
				2. decision 只能是 proceed、need_clarification、reject 三种之一。
				3. 只有在能够基于召回的 Schema 和知识完成任务时，才输出 decision=proceed。
				4. 如果关键实体、字段、业务定义在 Schema/知识中找不到，请输出 decision=need_clarification，不要硬规划。
				5. 如果用户请求包含危险操作、越权导出、破坏性意图，请输出 decision=reject。
				6. 当 decision=proceed 时，创建 1 到 %d 个步骤；当不是 proceed 时，steps 必须为空数组。
				7. 每个步骤的 instruction 必须是自包含的，能被 SQL 生成器直接执行。
				8. 只允许使用召回 Schema 中真实存在的表和字段，不要编造。
				9. tables 列出本计划实际依赖的表；columns 列出关键列，便于后续校验。
				10. 优先使用最少步骤数。
				11. 如果之前的计划校验失败，明确修复问题。

				# 思考路径
				1. 理解目标：用户的核心疑问是什么？
				2. 核对 Schema：检查计划查询的字段是否在 Schema 中真实存在。
				3. 先做决策：判断是 proceed、need_clarification 还是 reject。
				4. 拆解步骤：只有在 proceed 时，将大问题拆解为可执行的 SQL 步骤。
				5. 撰写指令：确保每个步骤的 instruction 足够详细，让 SQL 生成器一看就懂。

				# 用户请求
				%s

				# 规范化查询
				%s

				# 多轮上下文
				%s

				# Schema 上下文
				%s

				# 业务知识
				%s

				# 文档定义
				%s
				""".formatted(maxSteps, safe(state.getQuery()), safe(state.getCanonicalQuery()),
					safeOrDefault(state.getMultiTurnContext(), "(无)"), safeOrDefault(state.getRecalledSchemaText(), "(无)"),
					safeOrDefault(state.getEvidenceText(), "(无)"), safeOrDefault(state.getDocumentText(), "(无)")));

		if (StringUtils.hasText(state.getPlanValidationError())) {
			prompt.append("\n# 之前的计划校验错误\n").append(state.getPlanValidationError()).append('\n');
			prompt.append("\n# 之前的原始计划\n").append(safeOrDefault(state.getPlannerRawOutput(), "(无)")).append('\n');
		}
		return prompt.toString().trim();
	}

	private PlannerOutput parsePlannerOutput(String raw, SearchLiteState state) {
		String query = resolvePlanQuery(state);
		List<SearchLitePlanStep> fallback = List.of(new SearchLitePlanStep(1, query));
		if (!StringUtils.hasText(raw)) {
			return new PlannerOutput("proceed", "", List.of(), List.of(), fallback);
		}
		try {
			String json = extractJsonObject(raw.trim());
			PlannerOutputPayload payload = objectMapper.readValue(json, PlannerOutputPayload.class);
			List<SearchLitePlanStep> normalized = normalizeSteps(payload == null ? null : payload.steps(), query);
			String normalizedDecision = normalizeDecision(payload == null ? null : payload.decision());
			String reason = safe(payload == null ? null : payload.reason());
			List<String> tables = normalizeStringList(payload == null ? null : payload.tables());
			List<String> columns = normalizeStringList(payload == null ? null : payload.columns());
			if (!"proceed".equals(normalizedDecision)) {
				return new PlannerOutput(normalizedDecision, reason, tables, columns, List.of());
			}
			return new PlannerOutput(normalizedDecision, reason, tables, columns,
					normalized.isEmpty() ? fallback : normalized);
		}
		catch (Exception ex) {
			log.warn("planner output parse failed, fallback to single-step plan: {}", ex.getMessage());
			return new PlannerOutput("proceed", "", List.of(), List.of(), fallback);
		}
	}

	private void applyPlannerDecision(PlannerOutput plannerOutput, SearchLiteState state) {
		String decision = normalizeDecision(plannerOutput.decision());
		String reason = safe(plannerOutput.reason());
		if (!"proceed".equals(decision)) {
			state.setPlanSteps(List.of());
			state.setPlannerEnabled(false);
			state.setPlanFinished(true);
			state.setCurrentPlanStepIndex(0);
			state.setPlanFinishedReason(decision);
			if ("need_clarification".equals(decision)) {
				state.setResultMode("need_clarification");
				state.setFeasibilityResult("需要澄清");
				state.setFeasibilityMessage(reason);
			}
			else {
				state.setResultMode("need_clarification");
				state.setFeasibilityResult("自由闲聊");
				state.setFeasibilityMessage(StringUtils.hasText(reason) ? reason : "当前请求不允许执行。");
			}
			return;
		}

		Set<String> recalledTables = new HashSet<>(normalizeStringList(state.getRecalledTables()));
		if (!recalledTables.isEmpty() && !plannerOutput.tables().isEmpty()
				&& !recalledTables.containsAll(normalizeStringList(plannerOutput.tables()))) {
			state.setPlannerDecision("need_clarification");
			state.setPlannerDecisionReason("计划依赖了召回 schema 中不存在的表，请补充更明确的查询条件。");
			state.setPlanSteps(List.of());
			state.setPlannerEnabled(false);
			state.setPlanFinished(true);
			state.setCurrentPlanStepIndex(0);
			state.setPlanFinishedReason("need_clarification");
			state.setResultMode("need_clarification");
			state.setFeasibilityResult("需要澄清");
			state.setFeasibilityMessage(state.getPlannerDecisionReason());
			return;
		}

		if (plannerOutput.steps().isEmpty()) {
			state.setPlannerDecision("need_clarification");
			state.setPlannerDecisionReason("当前请求缺少足够信息，暂时无法形成可执行计划。");
			state.setPlanFinished(true);
			state.setPlanFinishedReason("need_clarification");
			state.setResultMode("need_clarification");
			state.setFeasibilityResult("需要澄清");
			state.setFeasibilityMessage(state.getPlannerDecisionReason());
		}
	}

	private List<SearchLitePlanStep> normalizeSteps(List<PlannerOutputStep> rawSteps, String fallbackQuery) {
		if (rawSteps == null || rawSteps.isEmpty()) {
			return List.of();
		}
		List<SearchLitePlanStep> normalized = new ArrayList<>();
		int nextStep = 1;
		for (PlannerOutputStep rawStep : rawSteps) {
			if (rawStep == null || !StringUtils.hasText(rawStep.instruction())) {
				continue;
			}
			if (!"SQL".equalsIgnoreCase(safeOrDefault(rawStep.tool(), "SQL"))) {
				continue;
			}
			SearchLitePlanStep step = new SearchLitePlanStep(nextStep++, rawStep.instruction().trim());
			step.setTool("SQL");
			step.setStatus("PENDING");
			normalized.add(step);
			if (normalized.size() >= maxSteps) {
				break;
			}
		}
		if (normalized.isEmpty() && StringUtils.hasText(fallbackQuery)) {
			normalized.add(new SearchLitePlanStep(1, fallbackQuery));
		}
		return normalized;
	}

	private String extractJsonObject(String text) {
		int start = text.indexOf('{');
		int end = text.lastIndexOf('}');
		if (start >= 0 && end > start) {
			return text.substring(start, end + 1);
		}
		return text;
	}

	private String resolvePlanQuery(SearchLiteState state) {
		if (StringUtils.hasText(state.getCanonicalQuery())) {
			return state.getCanonicalQuery();
		}
		if (StringUtils.hasText(state.getContextualizedQuery())) {
			return state.getContextualizedQuery();
		}
		return safe(state.getQuery());
	}

	private String resolveThreadId(SearchLiteState state) {
		if (StringUtils.hasText(state.getThreadId())) {
			return state.getThreadId();
		}
		String generated = "graph-planner-" + UUID.randomUUID();
		state.setThreadId(generated);
		return generated;
	}

	private String safe(String value) {
		return value == null ? "" : value.trim();
	}

	private String safeOrDefault(String value, String fallback) {
		return StringUtils.hasText(value) ? value.trim() : fallback;
	}

	private String normalizeDecision(String decision) {
		String normalized = safe(decision).toLowerCase();
		return switch (normalized) {
			case "need_clarification", "reject", "proceed" -> normalized;
			default -> "proceed";
		};
	}

	private List<String> normalizeStringList(List<String> values) {
		if (values == null || values.isEmpty()) {
			return List.of();
		}
		return values.stream().filter(StringUtils::hasText).map(String::trim).distinct().toList();
	}

	private record PlannerOutput(String decision, String reason, List<String> tables, List<String> columns,
			List<SearchLitePlanStep> steps) {
	}

	private record PlannerOutputPayload(String decision, String reason, List<String> tables, List<String> columns,
			List<PlannerOutputStep> steps) {
	}

	private record PlannerOutputStep(Integer step, String instruction, String tool) {
	}

}
