package com.alibaba.cloud.ai.dataagentbackend.lite.trace;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLitePlanStep;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class SearchLiteTraceSummarizer {

	private SearchLiteTraceSummarizer() {
	}

	static Map<String, Object> summarizeInput(SearchLiteStage stage, SearchLiteState state) {
		Map<String, Object> summary = new LinkedHashMap<>();
		summary.put("query", safe(state.getQuery()));
		summary.put("canonicalQuery", safe(state.getCanonicalQuery()));
		summary.put("recallQuery", safe(state.getRecallQuery()));
		summary.put("effectiveQuery", safe(state.getEffectiveQuery()));
		summary.put("currentPlanStepIndex", state.getCurrentPlanStepIndex());
		if (stage == SearchLiteStage.PLANNER || stage == SearchLiteStage.PLAN_EXECUTOR
				|| stage == SearchLiteStage.HUMAN_FEEDBACK) {
			summary.put("planSteps", summarizePlanSteps(state.getPlanSteps()));
			summary.put("planRepairCount", state.getPlanRepairCount());
			summary.put("humanReviewEnabled", state.isHumanReviewEnabled());
			summary.put("humanFeedbackStatus", safe(state.getHumanFeedbackStatus()));
		}
		if (stage == SearchLiteStage.SCHEMA_RECALL) {
			summary.put("schemaTableCount", size(state.getSchemaTableDetails()));
			summary.put("schemaTextLen", length(state.getSchemaText()));
			summary.put("evidenceTextLen", length(state.getEvidenceText()));
		}
		if (stage == SearchLiteStage.SQL_GENERATE || stage == SearchLiteStage.SQL_EXECUTE) {
			summary.put("recalledTables", List.copyOf(state.getRecalledTables()));
			summary.put("sqlRetryCount", state.getSqlRetryCount());
			summary.put("sqlRetryReason", safe(state.getSqlRetryReason()));
		}
		return summary;
	}

	static Map<String, Object> summarizeOutput(SearchLiteStage stage, SearchLiteState state) {
		Map<String, Object> summary = new LinkedHashMap<>();
		summary.put("intentClassification", safe(state.getIntentClassification()));
		summary.put("resultMode", safe(state.getResultMode()));
		summary.put("error", safe(state.getError()));
		if (stage == SearchLiteStage.SCHEMA_RECALL) {
			summary.put("recalledTables", List.copyOf(state.getRecalledTables()));
			summary.put("recalledSchemaTextLen", length(state.getRecalledSchemaText()));
			summary.put("focusedColumnTableCount", size(state.getRecalledTables()));
		}
		if (stage == SearchLiteStage.PLANNER || stage == SearchLiteStage.PLAN_EXECUTOR
				|| stage == SearchLiteStage.HUMAN_FEEDBACK) {
			summary.put("planSteps", summarizePlanSteps(state.getPlanSteps()));
			summary.put("plannerEnabled", state.isPlannerEnabled());
			summary.put("planValidationStatus", state.isPlanValidationStatus());
			summary.put("planValidationError", safe(state.getPlanValidationError()));
			summary.put("planRepairCount", state.getPlanRepairCount());
			summary.put("planFinished", state.isPlanFinished());
			summary.put("planFinishedReason", safe(state.getPlanFinishedReason()));
			summary.put("awaitingHumanFeedback", state.isAwaitingHumanFeedback());
		}
		if (stage == SearchLiteStage.SQL_GENERATE || stage == SearchLiteStage.SQL_EXECUTE
				|| stage == SearchLiteStage.RESULT) {
			summary.put("sql", safe(state.getSql()));
			summary.put("sqlRetryCount", state.getSqlRetryCount());
			summary.put("sqlRetryReason", safe(state.getSqlRetryReason()));
			summary.put("rowCount", size(state.getRows()));
			summary.put("resultSummaryLen", length(state.getResultSummary()));
		}
		return summary;
	}

	static Map<String, Object> summarizePlanSteps(List<SearchLitePlanStep> steps) {
		if (steps == null || steps.isEmpty()) {
			return Map.of("count", 0, "steps", List.of());
		}
		List<Map<String, Object>> normalized = steps.stream().map(step -> Map.<String, Object>of("step", step.getStep(),
				"instruction", safe(step.getInstruction()), "tool", safe(step.getTool()), "status", safe(step.getStatus()),
				"rowCount", step.getRowCount(), "error", safe(step.getError()))).toList();
		return Map.of("count", steps.size(), "steps", normalized);
	}

	private static int length(String value) {
		return value == null ? 0 : value.length();
	}

	private static int size(List<?> list) {
		return list == null ? 0 : list.size();
	}

	private static String safe(String value) {
		return value == null ? "" : value.trim();
	}

}
