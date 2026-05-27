package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaColumn;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaForeignKey;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.graph.OverAllState;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class SearchLiteGraphStateMapper {

	private SearchLiteGraphStateMapper() {
	}

	public static Map<String, Object> fromSearchLiteState(SearchLiteState state) {
		HashMap<String, Object> values = new HashMap<>();
		if (state == null) {
			return values;
		}
		values.put(SearchLiteGraphStateKeys.AGENT_ID, state.getAgentId());
		values.put(SearchLiteGraphStateKeys.THREAD_ID, state.getThreadId());
		values.put(SearchLiteGraphStateKeys.QUERY, state.getQuery());
		values.put(SearchLiteGraphStateKeys.MULTI_TURN_CONTEXT, state.getMultiTurnContext());
		values.put(SearchLiteGraphStateKeys.CONTEXTUALIZED_QUERY, state.getContextualizedQuery());
		values.put(SearchLiteGraphStateKeys.INTENT_CLASSIFICATION, state.getIntentClassification());
		values.put(SearchLiteGraphStateKeys.EVIDENCES, state.getEvidences());
		values.put(SearchLiteGraphStateKeys.EVIDENCE_TEXT, state.getEvidenceText());
		values.put(SearchLiteGraphStateKeys.EVIDENCE_REWRITE_QUERY, state.getEvidenceRewriteQuery());
		values.put(SearchLiteGraphStateKeys.DOCUMENT_TEXT, state.getDocumentText());
		values.put(SearchLiteGraphStateKeys.SCHEMA_TABLES, state.getSchemaTables());
		values.put(SearchLiteGraphStateKeys.SCHEMA_TEXT, state.getSchemaText());
		values.put(SearchLiteGraphStateKeys.SCHEMA_TABLE_DETAILS, state.getSchemaTableDetails());
		values.put(SearchLiteGraphStateKeys.RECALLED_TABLES, state.getRecalledTables());
		values.put(SearchLiteGraphStateKeys.RECALLED_SCHEMA_TEXT, state.getRecalledSchemaText());
		values.put(SearchLiteGraphStateKeys.CANONICAL_QUERY, state.getCanonicalQuery());
		values.put(SearchLiteGraphStateKeys.EXPANDED_QUERIES, state.getExpandedQueries());
		values.put(SearchLiteGraphStateKeys.FEASIBILITY_RESULT, state.getFeasibilityResult());
		values.put(SearchLiteGraphStateKeys.FEASIBILITY_MESSAGE, state.getFeasibilityMessage());
		values.put(SearchLiteGraphStateKeys.HUMAN_REVIEW_ENABLED, state.isHumanReviewEnabled());
		values.put(SearchLiteGraphStateKeys.HUMAN_FEEDBACK_STATUS, state.getHumanFeedbackStatus());
		values.put(SearchLiteGraphStateKeys.HUMAN_FEEDBACK_COMMENT, state.getHumanFeedbackComment());
		values.put(SearchLiteGraphStateKeys.AWAITING_HUMAN_FEEDBACK, state.isAwaitingHumanFeedback());
		values.put(SearchLiteGraphStateKeys.PLAN_STEPS, state.getPlanSteps());
		values.put(SearchLiteGraphStateKeys.CURRENT_PLAN_STEP_INDEX, state.getCurrentPlanStepIndex());
		values.put(SearchLiteGraphStateKeys.PLANNER_ENABLED, state.isPlannerEnabled());
		values.put(SearchLiteGraphStateKeys.PLAN_FINISHED, state.isPlanFinished());
		values.put(SearchLiteGraphStateKeys.PLAN_FINISHED_REASON, state.getPlanFinishedReason());
		values.put(SearchLiteGraphStateKeys.PLANNER_RAW_OUTPUT, state.getPlannerRawOutput());
		values.put(SearchLiteGraphStateKeys.PLAN_VALIDATION_STATUS, state.isPlanValidationStatus());
		values.put(SearchLiteGraphStateKeys.PLAN_VALIDATION_ERROR, state.getPlanValidationError());
		values.put(SearchLiteGraphStateKeys.PLAN_REPAIR_COUNT, state.getPlanRepairCount());
		values.put(SearchLiteGraphStateKeys.SQL, state.getSql());
		values.put(SearchLiteGraphStateKeys.SQL_RETRY_COUNT, state.getSqlRetryCount());
		values.put(SearchLiteGraphStateKeys.LAST_FAILED_SQL, state.getLastFailedSql());
		values.put(SearchLiteGraphStateKeys.SQL_RETRY_REASON, state.getSqlRetryReason());
		values.put(SearchLiteGraphStateKeys.ROWS, state.getRows());
		values.put(SearchLiteGraphStateKeys.RESULT_SUMMARY, state.getResultSummary());
		values.put(SearchLiteGraphStateKeys.RESULT_MODE, state.getResultMode());
		values.put(SearchLiteGraphStateKeys.ERROR, state.getError());
		return values;
	}

	public static SearchLiteState toSearchLiteState(OverAllState graphState) {
		SearchLiteState state = new SearchLiteState();
		if (graphState == null) {
			return state;
		}
		state.setAgentId(get(graphState, SearchLiteGraphStateKeys.AGENT_ID, String.class));
		state.setThreadId(get(graphState, SearchLiteGraphStateKeys.THREAD_ID, String.class));
		state.setQuery(get(graphState, SearchLiteGraphStateKeys.QUERY, String.class));
		state.setMultiTurnContext(get(graphState, SearchLiteGraphStateKeys.MULTI_TURN_CONTEXT, String.class));
		state.setContextualizedQuery(get(graphState, SearchLiteGraphStateKeys.CONTEXTUALIZED_QUERY, String.class));
		state.setIntentClassification(get(graphState, SearchLiteGraphStateKeys.INTENT_CLASSIFICATION, String.class));
		state.setEvidences(get(graphState, SearchLiteGraphStateKeys.EVIDENCES, java.util.List.class));
		state.setEvidenceText(get(graphState, SearchLiteGraphStateKeys.EVIDENCE_TEXT, String.class));
		state.setEvidenceRewriteQuery(get(graphState, SearchLiteGraphStateKeys.EVIDENCE_REWRITE_QUERY, String.class));
		state.setDocumentText(get(graphState, SearchLiteGraphStateKeys.DOCUMENT_TEXT, String.class));
		state.setSchemaTables(get(graphState, SearchLiteGraphStateKeys.SCHEMA_TABLES, java.util.List.class));
		state.setSchemaText(get(graphState, SearchLiteGraphStateKeys.SCHEMA_TEXT, String.class));
		state.setSchemaTableDetails(getSchemaTableDetails(graphState));
		state.setRecalledTables(get(graphState, SearchLiteGraphStateKeys.RECALLED_TABLES, java.util.List.class));
		state.setRecalledSchemaText(get(graphState, SearchLiteGraphStateKeys.RECALLED_SCHEMA_TEXT, String.class));
		state.setCanonicalQuery(get(graphState, SearchLiteGraphStateKeys.CANONICAL_QUERY, String.class));
		state.setExpandedQueries(get(graphState, SearchLiteGraphStateKeys.EXPANDED_QUERIES, java.util.List.class));
		state.setFeasibilityResult(get(graphState, SearchLiteGraphStateKeys.FEASIBILITY_RESULT, String.class));
		state.setFeasibilityMessage(get(graphState, SearchLiteGraphStateKeys.FEASIBILITY_MESSAGE, String.class));
		Boolean humanReviewEnabled = get(graphState, SearchLiteGraphStateKeys.HUMAN_REVIEW_ENABLED, Boolean.class);
		state.setHumanReviewEnabled(Boolean.TRUE.equals(humanReviewEnabled));
		state.setHumanFeedbackStatus(get(graphState, SearchLiteGraphStateKeys.HUMAN_FEEDBACK_STATUS, String.class));
		state.setHumanFeedbackComment(get(graphState, SearchLiteGraphStateKeys.HUMAN_FEEDBACK_COMMENT, String.class));
		Boolean awaitingHumanFeedback = get(graphState, SearchLiteGraphStateKeys.AWAITING_HUMAN_FEEDBACK, Boolean.class);
		state.setAwaitingHumanFeedback(Boolean.TRUE.equals(awaitingHumanFeedback));
		state.setPlanSteps(get(graphState, SearchLiteGraphStateKeys.PLAN_STEPS, java.util.List.class));
		Integer stepIndex = get(graphState, SearchLiteGraphStateKeys.CURRENT_PLAN_STEP_INDEX, Integer.class);
		state.setCurrentPlanStepIndex(stepIndex == null ? 0 : stepIndex);
		Boolean plannerEnabled = get(graphState, SearchLiteGraphStateKeys.PLANNER_ENABLED, Boolean.class);
		state.setPlannerEnabled(Boolean.TRUE.equals(plannerEnabled));
		Boolean planFinished = get(graphState, SearchLiteGraphStateKeys.PLAN_FINISHED, Boolean.class);
		state.setPlanFinished(Boolean.TRUE.equals(planFinished));
		state.setPlanFinishedReason(get(graphState, SearchLiteGraphStateKeys.PLAN_FINISHED_REASON, String.class));
		state.setPlannerRawOutput(get(graphState, SearchLiteGraphStateKeys.PLANNER_RAW_OUTPUT, String.class));
		Boolean planValidationStatus = get(graphState, SearchLiteGraphStateKeys.PLAN_VALIDATION_STATUS, Boolean.class);
		state.setPlanValidationStatus(planValidationStatus == null || planValidationStatus);
		state.setPlanValidationError(get(graphState, SearchLiteGraphStateKeys.PLAN_VALIDATION_ERROR, String.class));
		Integer planRepairCount = get(graphState, SearchLiteGraphStateKeys.PLAN_REPAIR_COUNT, Integer.class);
		state.setPlanRepairCount(planRepairCount == null ? 0 : planRepairCount);
		state.setSql(get(graphState, SearchLiteGraphStateKeys.SQL, String.class));
		Integer retryCount = get(graphState, SearchLiteGraphStateKeys.SQL_RETRY_COUNT, Integer.class);
		state.setSqlRetryCount(retryCount == null ? 0 : retryCount);
		state.setLastFailedSql(get(graphState, SearchLiteGraphStateKeys.LAST_FAILED_SQL, String.class));
		state.setSqlRetryReason(get(graphState, SearchLiteGraphStateKeys.SQL_RETRY_REASON, String.class));
		state.setRows(get(graphState, SearchLiteGraphStateKeys.ROWS, java.util.List.class));
		state.setResultSummary(get(graphState, SearchLiteGraphStateKeys.RESULT_SUMMARY, String.class));
		state.setResultMode(get(graphState, SearchLiteGraphStateKeys.RESULT_MODE, String.class));
		state.setError(get(graphState, SearchLiteGraphStateKeys.ERROR, String.class));
		return state;
	}

	@SuppressWarnings("unchecked")
	private static <T> T get(OverAllState graphState, String key, Class<?> type) {
		return (T) graphState.value(key).filter(type::isInstance).orElse(null);
	}

	@SuppressWarnings("unchecked")
	private static List<SchemaTable> getSchemaTableDetails(OverAllState graphState) {
		Object raw = graphState.value(SearchLiteGraphStateKeys.SCHEMA_TABLE_DETAILS).orElse(null);
		if (!(raw instanceof List<?> rawList)) {
			return new ArrayList<>();
		}
		List<SchemaTable> tables = new ArrayList<>(rawList.size());
		for (Object item : rawList) {
			SchemaTable table = toSchemaTable(item);
			if (table != null) {
				tables.add(table);
			}
		}
		return tables;
	}

	@SuppressWarnings("unchecked")
	private static SchemaTable toSchemaTable(Object raw) {
		if (raw instanceof SchemaTable schemaTable) {
			List<SchemaColumn> normalizedColumns = new ArrayList<>();
			if (schemaTable.columns() != null) {
				for (Object column : schemaTable.columns()) {
					SchemaColumn normalized = toSchemaColumn(column);
					if (normalized != null) {
						normalizedColumns.add(normalized);
					}
				}
			}
			List<SchemaForeignKey> normalizedForeignKeys = new ArrayList<>();
			if (schemaTable.foreignKeys() != null) {
				for (Object foreignKey : schemaTable.foreignKeys()) {
					SchemaForeignKey normalized = toSchemaForeignKey(foreignKey);
					if (normalized != null) {
						normalizedForeignKeys.add(normalized);
					}
				}
			}
			return new SchemaTable(schemaTable.name(), schemaTable.comment(), normalizedColumns, normalizedForeignKeys);
		}
		if (!(raw instanceof Map<?, ?> map)) {
			return null;
		}
		String name = toStringValue(map.get("name"));
		String comment = toStringValue(map.get("comment"));
		List<SchemaColumn> columns = new ArrayList<>();
		Object rawColumns = map.get("columns");
		if (rawColumns instanceof List<?> rawColumnList) {
			for (Object column : rawColumnList) {
				SchemaColumn schemaColumn = toSchemaColumn(column);
				if (schemaColumn != null) {
					columns.add(schemaColumn);
				}
			}
		}
		List<SchemaForeignKey> foreignKeys = new ArrayList<>();
		Object rawForeignKeys = map.get("foreignKeys");
		if (rawForeignKeys instanceof List<?> rawForeignKeyList) {
			for (Object fk : rawForeignKeyList) {
				SchemaForeignKey foreignKey = toSchemaForeignKey(fk);
				if (foreignKey != null) {
					foreignKeys.add(foreignKey);
				}
			}
		}
		return new SchemaTable(name, comment, columns, foreignKeys);
	}

	private static SchemaColumn toSchemaColumn(Object raw) {
		if (raw instanceof SchemaColumn schemaColumn) {
			return schemaColumn;
		}
		if (!(raw instanceof Map<?, ?> map)) {
			return null;
		}
		return new SchemaColumn(
				toStringValue(map.get("name")),
				toStringValue(map.get("dataType")),
				toStringValue(map.get("columnType")),
				toBooleanValue(map.get("notNull")),
				toBooleanValue(map.get("primaryKey")),
				toStringValue(map.get("comment")));
	}

	private static SchemaForeignKey toSchemaForeignKey(Object raw) {
		if (raw instanceof SchemaForeignKey schemaForeignKey) {
			return schemaForeignKey;
		}
		if (!(raw instanceof Map<?, ?> map)) {
			return null;
		}
		return new SchemaForeignKey(
				toStringValue(map.get("columnName")),
				toStringValue(map.get("refTableName")),
				toStringValue(map.get("refColumnName")));
	}

	private static String toStringValue(Object value) {
		return value == null ? null : String.valueOf(value);
	}

	private static boolean toBooleanValue(Object value) {
		if (value instanceof Boolean bool) {
			return bool;
		}
		return value != null && Boolean.parseBoolean(String.valueOf(value));
	}

}
