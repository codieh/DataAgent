package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLitePlanStep;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphMessageEmitter;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateMapper;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

@Component
public class SearchLitePlanExecutorGraphNode implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLitePlanExecutorGraphNode.class);

	private static final int PREVIEW_LIMIT = 5;

	private final SearchLiteGraphMessageEmitter messageEmitter;

	private final int maxRepairAttempts;

	public SearchLitePlanExecutorGraphNode(SearchLiteGraphMessageEmitter messageEmitter,
			@Value("${search.lite.graph.planner.max-repair-attempts:2}") int maxRepairAttempts) {
		this.messageEmitter = Objects.requireNonNull(messageEmitter, "messageEmitter");
		this.maxRepairAttempts = Math.max(0, maxRepairAttempts);
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		SearchLiteState liteState = SearchLiteGraphStateMapper.toSearchLiteState(state);
		SearchLiteContext context = new SearchLiteContext(resolveThreadId(liteState));
		ensurePlan(liteState);
		String validationError = validatePlan(liteState);
		if (validationError != null) {
			liteState.setPlanValidationStatus(false);
			liteState.setPlanValidationError(validationError);
			liteState.setPlanRepairCount(liteState.getPlanRepairCount() + 1);
			if (liteState.getPlanRepairCount() > maxRepairAttempts) {
				liteState.setPlanFinished(true);
				liteState.setPlanFinishedReason("repair_exhausted");
				liteState.setError("计划生成失败：" + validationError);
			}
			emitPlanExecutorState(context, liteState, "计划校验失败，准备修复。");
			log.warn("graph plan-executor validation failed: repairCount={}, error={}", liteState.getPlanRepairCount(),
					validationError);
			return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
		}

		liteState.setPlanValidationStatus(true);
		liteState.setPlanValidationError(null);
		if (!liteState.isPlanFinished()) {
			liteState.setPlanFinishedReason(null);
		}
		completeRunningStepIfNeeded(liteState);
		prepareNextStepIfNeeded(liteState);
		emitPlanExecutorState(context, liteState, resolveProgressMessage(liteState));
		log.info("graph plan-executor node invoked: index={}, total={}, finished={}",
				liteState.getCurrentPlanStepIndex(), liteState.getPlanSteps().size(), liteState.isPlanFinished());
		return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
	}

	private void ensurePlan(SearchLiteState state) {
		if (state.getPlanSteps() != null && !state.getPlanSteps().isEmpty()) {
			return;
		}
		SearchLitePlanStep step = new SearchLitePlanStep(1, state.getEffectiveQuery());
		step.setTool("SQL");
		step.setStatus("PENDING");
		state.setPlanSteps(List.of(step));
		state.setCurrentPlanStepIndex(0);
		state.setPlanFinished(false);
		state.setPlanFinishedReason(null);
	}

	private String validatePlan(SearchLiteState state) {
		List<SearchLitePlanStep> steps = state.getPlanSteps();
		if (steps == null || steps.isEmpty()) {
			return "execution plan is empty";
		}
		int expectedStep = 1;
		for (SearchLitePlanStep step : steps) {
			if (step == null) {
				return "execution plan contains null step";
			}
			if (step.getStep() != expectedStep) {
				return "step numbering is not contiguous";
			}
			if (!StringUtils.hasText(step.getInstruction())) {
				return "step " + step.getStep() + " is missing instruction";
			}
			if (!"SQL".equalsIgnoreCase(StringUtils.hasText(step.getTool()) ? step.getTool() : "SQL")) {
				return "step " + step.getStep() + " has unsupported tool " + step.getTool();
			}
			expectedStep++;
		}
		if (state.getCurrentPlanStepIndex() < 0) {
			return "current plan step index is invalid";
		}
		return null;
	}

	private void completeRunningStepIfNeeded(SearchLiteState state) {
		SearchLitePlanStep current = state.getCurrentPlanStep();
		if (current == null || !"RUNNING".equalsIgnoreCase(current.getStatus())) {
			return;
		}
		if (!hasStepExecutionResult(state)) {
			return;
		}
		current.setSql(state.getSql());
		current.setRowCount(state.getRows() == null ? 0 : state.getRows().size());
		current.setPreviewRows(previewRows(state));
		current.setError(state.getError());
		current.setSummarySnippet(buildSummarySnippet(state, current));
		current.setStatus(StringUtils.hasText(state.getError()) ? "FAILED" : "DONE");
		state.setCurrentPlanStepIndex(state.getCurrentPlanStepIndex() + 1);
		if (StringUtils.hasText(state.getError())) {
			state.setPlanFinished(true);
			state.setPlanFinishedReason(resolveFailureReason(state));
		}
	}

	private boolean hasStepExecutionResult(SearchLiteState state) {
		return StringUtils.hasText(state.getSql()) || StringUtils.hasText(state.getError())
				|| (state.getResultMode() != null && state.getResultMode().startsWith("blocked_"));
	}

	private void prepareNextStepIfNeeded(SearchLiteState state) {
		if (state.isPlanFinished()) {
			return;
		}
		SearchLitePlanStep next = state.getCurrentPlanStep();
		if (next == null) {
			state.setPlanFinished(true);
			state.setPlanFinishedReason("all_steps_completed");
			return;
		}
		if ("PENDING".equalsIgnoreCase(next.getStatus())) {
			next.setStatus("RUNNING");
			clearStepRuntimeState(state);
		}
	}

	private void clearStepRuntimeState(SearchLiteState state) {
		state.setSql(null);
		state.setRows(List.of());
		state.setError(null);
		state.setResultSummary(null);
		state.setResultMode(null);
		state.setLastFailedSql(null);
		state.setSqlRetryReason(null);
		state.setSqlRetryCount(0);
	}

	private List<Map<String, Object>> previewRows(SearchLiteState state) {
		if (state.getRows() == null || state.getRows().isEmpty()) {
			return List.of();
		}
		return new ArrayList<>(state.getRows().stream().limit(PREVIEW_LIMIT).toList());
	}

	private String buildSummarySnippet(SearchLiteState state, SearchLitePlanStep current) {
		if (current == null) {
			return "";
		}
		if (StringUtils.hasText(state.getError())) {
			return "执行失败：" + state.getError();
		}
		if (StringUtils.hasText(state.getResultMode()) && state.getResultMode().startsWith("blocked_")) {
			return "执行被拦截：" + state.getResultMode();
		}
		if (current.getRowCount() <= 0) {
			return "执行成功，返回 0 行结果。";
		}
		return "执行成功，返回 %d 行结果，预览 %d 行。".formatted(current.getRowCount(), current.getPreviewRows().size());
	}

	private String resolveFailureReason(SearchLiteState state) {
		if (StringUtils.hasText(state.getResultMode()) && state.getResultMode().startsWith("blocked_")) {
			return state.getResultMode();
		}
		return "sql_execution_failed";
	}

	private String resolveProgressMessage(SearchLiteState state) {
		if (!state.isPlanValidationStatus()) {
			return "计划校验失败，准备修复。";
		}
		if (state.isPlanFinished()) {
			return "多步骤计划执行完成，正在汇总结果。";
		}
		SearchLitePlanStep current = state.getCurrentPlanStep();
		if (current == null) {
			return "多步骤计划执行完成，正在汇总结果。";
		}
		return "正在执行第 %d/%d 步：%s".formatted(current.getStep(), state.getPlanSteps().size(),
				current.getInstruction());
	}

	private void emitPlanExecutorState(SearchLiteContext context, SearchLiteState state, String message) {
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.message(context, SearchLiteStage.PLAN_EXECUTOR,
				SearchLiteMessageType.TEXT, message, null));
		messageEmitter.emitOne(context.threadId(), SearchLiteMessages.done(context, SearchLiteStage.PLAN_EXECUTOR,
				SearchLiteMessageType.JSON, null,
				Map.of("currentStepIndex", state.getCurrentPlanStepIndex(), "totalSteps", state.getPlanSteps().size(),
						"currentStep", currentStepPayload(state), "planValidationStatus", state.isPlanValidationStatus(),
						"planValidationError", safe(state.getPlanValidationError()), "planRepairCount",
						state.getPlanRepairCount(), "planFinished", state.isPlanFinished(), "planFinishedReason",
						safe(state.getPlanFinishedReason()))));
	}

	private Map<String, Object> currentStepPayload(SearchLiteState state) {
		SearchLitePlanStep current = state.getCurrentPlanStep();
		if (current == null) {
			return Map.of();
		}
		return Map.of("step", current.getStep(), "instruction", safe(current.getInstruction()), "status",
				safe(current.getStatus()));
	}

	private String safe(String value) {
		return value == null ? "" : value.trim();
	}

	private String resolveThreadId(SearchLiteState state) {
		if (StringUtils.hasText(state.getThreadId())) {
			return state.getThreadId();
		}
		String generated = "graph-plan-executor-" + UUID.randomUUID();
		state.setThreadId(generated);
		return generated;
	}

}
