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

	public String getEffectiveQuery() {
		if (canonicalQuery != null && !canonicalQuery.isBlank()) {
			return canonicalQuery.trim();
		}
		if (contextualizedQuery != null && !contextualizedQuery.isBlank()) {
			return contextualizedQuery.trim();
		}
		return query == null ? "" : query.trim();
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
		this.rows = rows == null ? new ArrayList<>() : rows;
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

}
