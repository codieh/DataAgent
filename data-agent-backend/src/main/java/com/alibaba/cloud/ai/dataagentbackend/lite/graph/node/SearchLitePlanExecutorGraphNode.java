package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLitePlanStep;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
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

@Component
public class SearchLitePlanExecutorGraphNode implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLitePlanExecutorGraphNode.class);

	private static final int PREVIEW_LIMIT = 5;

	private final int maxRepairAttempts;

	public SearchLitePlanExecutorGraphNode(
			@Value("${search.lite.graph.planner.max-repair-attempts:2}") int maxRepairAttempts) {
		this.maxRepairAttempts = Math.max(0, maxRepairAttempts);
	}

	@Override
	public Map<String, Object> apply(OverAllState state) {
		SearchLiteState liteState = SearchLiteGraphStateMapper.toSearchLiteState(state);
		ensurePlan(liteState);
		String validationError = validatePlan(liteState);
		if (validationError != null) {
			liteState.setPlanValidationStatus(false);
			liteState.setPlanValidationError(validationError);
			liteState.setPlanRepairCount(liteState.getPlanRepairCount() + 1);
			if (liteState.getPlanRepairCount() > maxRepairAttempts) {
				liteState.setPlanFinished(true);
				liteState.setError("计划生成失败：" + validationError);
			}
			log.warn("graph plan-executor validation failed: repairCount={}, error={}", liteState.getPlanRepairCount(),
					validationError);
			return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
		}

		liteState.setPlanValidationStatus(true);
		liteState.setPlanValidationError(null);
		completeRunningStepIfNeeded(liteState);
		prepareNextStepIfNeeded(liteState);
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
		current.setStatus(StringUtils.hasText(state.getError()) ? "FAILED" : "DONE");
		state.setCurrentPlanStepIndex(state.getCurrentPlanStepIndex() + 1);
		if (StringUtils.hasText(state.getError())) {
			state.setPlanFinished(true);
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

}
