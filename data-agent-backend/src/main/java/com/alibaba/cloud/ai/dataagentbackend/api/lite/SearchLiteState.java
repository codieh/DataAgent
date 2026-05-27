package com.alibaba.cloud.ai.dataagentbackend.api.lite;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * A mutable per-request state object for the lite pipeline.
 */
public class SearchLiteState {

	private String agentId;

	private String threadId;

	private String query;

	private String multiTurnContext;

	private String contextualizedQuery;

	// intent
	private String intentClassification;

	// evidence
	private List<EvidenceItem> evidences = new ArrayList<>();

	private String evidenceText;

	private String evidenceRewriteQuery;

	private String documentText;

	// schema
	private List<String> schemaTables = new ArrayList<>();

	private String schemaText;

	private List<SchemaTable> schemaTableDetails = new ArrayList<>();

	private List<String> recalledTables = new ArrayList<>();

	private String recalledSchemaText;

	// enhance
	private String canonicalQuery;

	private List<String> expandedQueries = new ArrayList<>();

	// feasibility
	private String feasibilityResult;

	private String feasibilityMessage;

	// human review
	private boolean humanReviewEnabled;

	private String humanFeedbackStatus;

	private String humanFeedbackComment;

	private boolean awaitingHumanFeedback;

	// planner
	private List<SearchLitePlanStep> planSteps = new ArrayList<>();

	private int currentPlanStepIndex;

	private boolean plannerEnabled;

	private boolean planFinished;

	private String planFinishedReason;

	private String plannerRawOutput;

	private boolean planValidationStatus = true;

	private String planValidationError;

	private int planRepairCount;

	// sql
	private String sql;

	private int sqlRetryCount;

	private String lastFailedSql;

	private String sqlRetryReason;

	// execution result
	private List<Map<String, Object>> rows = new ArrayList<>();

	private String resultSummary;

	private String resultMode;

	private String error;

	public static SearchLiteState fromRequest(SearchLiteRequest request) {
		SearchLiteState state = new SearchLiteState();
		state.agentId = request.agentId();
		state.threadId = request.threadId();
		state.query = request.query();
		state.humanReviewEnabled = request.humanReviewEnabled();
		if (request.humanFeedbackApproved() != null) {
			state.humanFeedbackStatus = request.humanFeedbackApproved() ? "APPROVED" : "REJECTED";
		}
		state.humanFeedbackComment = request.humanFeedbackComment();
		return state;
	}

	public String getAgentId() {
		return agentId;
	}

	public void setAgentId(String agentId) {
		this.agentId = agentId;
	}

	public String getThreadId() {
		return threadId;
	}

	public void setThreadId(String threadId) {
		this.threadId = threadId;
	}

	public String getQuery() {
		return query;
	}

	public void setQuery(String query) {
		this.query = query;
	}

	public String getMultiTurnContext() {
		return multiTurnContext;
	}

	public void setMultiTurnContext(String multiTurnContext) {
		this.multiTurnContext = multiTurnContext;
	}

	public String getContextualizedQuery() {
		return contextualizedQuery;
	}

	public void setContextualizedQuery(String contextualizedQuery) {
		this.contextualizedQuery = contextualizedQuery;
	}

	public String getIntentClassification() {
		return intentClassification;
	}

	public void setIntentClassification(String intentClassification) {
		this.intentClassification = intentClassification;
	}

	public List<EvidenceItem> getEvidences() {
		return evidences;
	}

	public void setEvidences(List<EvidenceItem> evidences) {
		this.evidences = evidences == null ? new ArrayList<>() : evidences;
	}

	public String getEvidenceText() {
		return evidenceText;
	}

	public void setEvidenceText(String evidenceText) {
		this.evidenceText = evidenceText;
	}

	public String getEvidenceRewriteQuery() {
		return evidenceRewriteQuery;
	}

	public void setEvidenceRewriteQuery(String evidenceRewriteQuery) {
		this.evidenceRewriteQuery = evidenceRewriteQuery;
	}

	public String getDocumentText() {
		return documentText;
	}

	public void setDocumentText(String documentText) {
		this.documentText = documentText;
	}

	public List<String> getSchemaTables() {
		return schemaTables;
	}

	public void setSchemaTables(List<String> schemaTables) {
		this.schemaTables = schemaTables == null ? new ArrayList<>() : schemaTables;
	}

	public String getSchemaText() {
		return schemaText;
	}

	public void setSchemaText(String schemaText) {
		this.schemaText = schemaText;
	}

	public List<SchemaTable> getSchemaTableDetails() {
		return schemaTableDetails;
	}

	public void setSchemaTableDetails(List<SchemaTable> schemaTableDetails) {
		this.schemaTableDetails = schemaTableDetails == null ? new ArrayList<>() : schemaTableDetails;
	}

	public List<String> getRecalledTables() {
		return recalledTables;
	}

	public void setRecalledTables(List<String> recalledTables) {
		this.recalledTables = recalledTables == null ? new ArrayList<>() : recalledTables;
	}

	public String getRecalledSchemaText() {
		return recalledSchemaText;
	}

	public void setRecalledSchemaText(String recalledSchemaText) {
		this.recalledSchemaText = recalledSchemaText;
	}

	public String getCanonicalQuery() {
		return canonicalQuery;
	}

	public void setCanonicalQuery(String canonicalQuery) {
		this.canonicalQuery = canonicalQuery;
	}

	public List<String> getExpandedQueries() {
		return expandedQueries;
	}

	public void setExpandedQueries(List<String> expandedQueries) {
		this.expandedQueries = expandedQueries == null ? new ArrayList<>() : expandedQueries;
	}

	public String getFeasibilityResult() {
		return feasibilityResult;
	}

	public void setFeasibilityResult(String feasibilityResult) {
		this.feasibilityResult = feasibilityResult;
	}

	public String getFeasibilityMessage() {
		return feasibilityMessage;
	}

	public void setFeasibilityMessage(String feasibilityMessage) {
		this.feasibilityMessage = feasibilityMessage;
	}

	public boolean isHumanReviewEnabled() {
		return humanReviewEnabled;
	}

	public void setHumanReviewEnabled(boolean humanReviewEnabled) {
		this.humanReviewEnabled = humanReviewEnabled;
	}

	public String getHumanFeedbackStatus() {
		return humanFeedbackStatus;
	}

	public void setHumanFeedbackStatus(String humanFeedbackStatus) {
		this.humanFeedbackStatus = humanFeedbackStatus;
	}

	public String getHumanFeedbackComment() {
		return humanFeedbackComment;
	}

	public void setHumanFeedbackComment(String humanFeedbackComment) {
		this.humanFeedbackComment = humanFeedbackComment;
	}

	public boolean isAwaitingHumanFeedback() {
		return awaitingHumanFeedback;
	}

	public void setAwaitingHumanFeedback(boolean awaitingHumanFeedback) {
		this.awaitingHumanFeedback = awaitingHumanFeedback;
	}

	public String getEffectiveQuery() {
		String planInstruction = getCurrentPlanInstruction();
		if (planInstruction != null && !planInstruction.isBlank()) {
			return planInstruction.trim();
		}
		if (canonicalQuery != null && !canonicalQuery.isBlank()) {
			return canonicalQuery.trim();
		}
		if (contextualizedQuery != null && !contextualizedQuery.isBlank()) {
			return contextualizedQuery.trim();
		}
		return query == null ? "" : query.trim();
	}

	public List<SearchLitePlanStep> getPlanSteps() {
		return planSteps;
	}

	public void setPlanSteps(List<SearchLitePlanStep> planSteps) {
		this.planSteps = planSteps == null ? new ArrayList<>() : planSteps;
	}

	public int getCurrentPlanStepIndex() {
		return currentPlanStepIndex;
	}

	public void setCurrentPlanStepIndex(int currentPlanStepIndex) {
		this.currentPlanStepIndex = Math.max(0, currentPlanStepIndex);
	}

	public boolean isPlannerEnabled() {
		return plannerEnabled;
	}

	public void setPlannerEnabled(boolean plannerEnabled) {
		this.plannerEnabled = plannerEnabled;
	}

	public boolean isPlanFinished() {
		return planFinished;
	}

	public void setPlanFinished(boolean planFinished) {
		this.planFinished = planFinished;
	}

	public String getPlanFinishedReason() {
		return planFinishedReason;
	}

	public void setPlanFinishedReason(String planFinishedReason) {
		this.planFinishedReason = planFinishedReason;
	}

	public String getPlannerRawOutput() {
		return plannerRawOutput;
	}

	public void setPlannerRawOutput(String plannerRawOutput) {
		this.plannerRawOutput = plannerRawOutput;
	}

	public boolean isPlanValidationStatus() {
		return planValidationStatus;
	}

	public void setPlanValidationStatus(boolean planValidationStatus) {
		this.planValidationStatus = planValidationStatus;
	}

	public String getPlanValidationError() {
		return planValidationError;
	}

	public void setPlanValidationError(String planValidationError) {
		this.planValidationError = planValidationError;
	}

	public int getPlanRepairCount() {
		return planRepairCount;
	}

	public void setPlanRepairCount(int planRepairCount) {
		this.planRepairCount = Math.max(0, planRepairCount);
	}

	public SearchLitePlanStep getCurrentPlanStep() {
		if (planSteps == null || planSteps.isEmpty()) {
			return null;
		}
		if (currentPlanStepIndex < 0 || currentPlanStepIndex >= planSteps.size()) {
			return null;
		}
		return planSteps.get(currentPlanStepIndex);
	}

	public String getCurrentPlanInstruction() {
		SearchLitePlanStep current = getCurrentPlanStep();
		return current == null ? null : current.getInstruction();
	}

	public String getRecallQuery() {
		if (contextualizedQuery != null && !contextualizedQuery.isBlank()) {
			return contextualizedQuery.trim();
		}
		return query == null ? "" : query.trim();
	}

	public String getSql() {
		return sql;
	}

	public void setSql(String sql) {
		this.sql = sql;
	}

	public int getSqlRetryCount() {
		return sqlRetryCount;
	}

	public void setSqlRetryCount(int sqlRetryCount) {
		this.sqlRetryCount = Math.max(0, sqlRetryCount);
	}

	public String getLastFailedSql() {
		return lastFailedSql;
	}

	public void setLastFailedSql(String lastFailedSql) {
		this.lastFailedSql = lastFailedSql;
	}

	public String getSqlRetryReason() {
		return sqlRetryReason;
	}

	public void setSqlRetryReason(String sqlRetryReason) {
		this.sqlRetryReason = sqlRetryReason;
	}

	public List<Map<String, Object>> getRows() {
		return rows;
	}

	public void setRows(List<Map<String, Object>> rows) {
		this.rows = sanitizeRows(rows);
	}

	public String getResultSummary() {
		return resultSummary;
	}

	public void setResultSummary(String resultSummary) {
		this.resultSummary = resultSummary;
	}

	public String getResultMode() {
		return resultMode;
	}

	public void setResultMode(String resultMode) {
		this.resultMode = resultMode;
	}

	public String getError() {
		return error;
	}

	public void setError(String error) {
		this.error = error;
	}

	private List<Map<String, Object>> sanitizeRows(List<Map<String, Object>> rows) {
		if (rows == null) {
			return new ArrayList<>();
		}
		List<Map<String, Object>> sanitized = new ArrayList<>(rows.size());
		for (Map<String, Object> row : rows) {
			sanitized.add(sanitizeMap(row));
		}
		return sanitized;
	}

	@SuppressWarnings("unchecked")
	private Map<String, Object> sanitizeMap(Map<String, Object> raw) {
		Map<String, Object> sanitized = new java.util.LinkedHashMap<>();
		if (raw == null) {
			return sanitized;
		}
		for (Map.Entry<String, Object> entry : raw.entrySet()) {
			String key = entry.getKey();
			if ("@class".equals(key)) {
				continue;
			}
			sanitized.put(key, sanitizeValue(entry.getValue()));
		}
		return sanitized;
	}

	@SuppressWarnings("unchecked")
	private Object sanitizeValue(Object value) {
		if (value instanceof Map<?, ?> map) {
			Map<String, Object> nested = new java.util.LinkedHashMap<>();
			for (Map.Entry<?, ?> entry : map.entrySet()) {
				String key = String.valueOf(entry.getKey());
				if ("@class".equals(key)) {
					continue;
				}
				nested.put(key, sanitizeValue(entry.getValue()));
			}
			return nested;
		}
		if (value instanceof List<?> list) {
			List<Object> nested = new ArrayList<>(list.size());
			for (Object item : list) {
				nested.add(sanitizeValue(item));
			}
			return nested;
		}
		return value;
	}

}
