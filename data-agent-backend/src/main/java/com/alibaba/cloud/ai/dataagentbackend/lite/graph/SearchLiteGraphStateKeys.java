package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

public final class SearchLiteGraphStateKeys {

	private SearchLiteGraphStateKeys() {
	}

	public static final String AGENT_ID = "agentId";

	public static final String THREAD_ID = "threadId";

	public static final String QUERY = "query";

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

	public static final String SQL = "sql";

	public static final String ROWS = "rows";

	public static final String RESULT_SUMMARY = "resultSummary";

	public static final String ERROR = "error";

	public static final String GRAPH_MESSAGES = "graphMessages";

	public static final String GRAPH_ROUTE = "graphRoute";

}
