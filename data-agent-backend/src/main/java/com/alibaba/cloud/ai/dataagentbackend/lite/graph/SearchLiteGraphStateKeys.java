package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

public final class SearchLiteGraphStateKeys {

	private SearchLiteGraphStateKeys() {
	}

	public static final String AGENT_ID = "agentId";

	public static final String THREAD_ID = "threadId";

	public static final String QUERY = "query";

	public static final String MULTI_TURN_CONTEXT = "multiTurnContext";

	public static final String CONTEXTUALIZED_QUERY = "contextualizedQuery";

	public static final String INTENT_CLASSIFICATION = "intentClassification";

	public static final String EVIDENCES = "evidences";

	public static final String EVIDENCE_TEXT = "evidenceText";

	public static final String EVIDENCE_REWRITE_QUERY = "evidenceRewriteQuery";

	public static final String DOCUMENT_TEXT = "documentText";

	public static final String SCHEMA_TABLES = "schemaTables";

	public static final String SCHEMA_TEXT = "schemaText";

	public static final String SCHEMA_TABLE_DETAILS = "schemaTableDetails";

	public static final String RECALLED_TABLES = "recalledTables";

	public static final String RECALLED_SCHEMA_TEXT = "recalledSchemaText";

	public static final String CANONICAL_QUERY = "canonicalQuery";

	public static final String EXPANDED_QUERIES = "expandedQueries";

	public static final String PLAN_STEPS = "planSteps";

	public static final String CURRENT_PLAN_STEP_INDEX = "currentPlanStepIndex";

	public static final String PLANNER_ENABLED = "plannerEnabled";

	public static final String PLAN_FINISHED = "planFinished";

	public static final String PLANNER_RAW_OUTPUT = "plannerRawOutput";

	public static final String PLAN_VALIDATION_STATUS = "planValidationStatus";

	public static final String PLAN_VALIDATION_ERROR = "planValidationError";

	public static final String PLAN_REPAIR_COUNT = "planRepairCount";

	public static final String SQL = "sql";

	public static final String SQL_RETRY_COUNT = "sqlRetryCount";

	public static final String LAST_FAILED_SQL = "lastFailedSql";

	public static final String SQL_RETRY_REASON = "sqlRetryReason";

	public static final String ROWS = "rows";

	public static final String RESULT_SUMMARY = "resultSummary";

	public static final String RESULT_MODE = "resultMode";

	public static final String ERROR = "error";

	public static final String GRAPH_MESSAGES = "graphMessages";

	public static final String GRAPH_ROUTE = "graphRoute";

}
