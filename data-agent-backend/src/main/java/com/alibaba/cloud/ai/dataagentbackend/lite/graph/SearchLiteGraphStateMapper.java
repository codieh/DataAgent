package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;

import java.util.HashMap;
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
		values.put(SearchLiteGraphStateKeys.SQL, state.getSql());
		values.put(SearchLiteGraphStateKeys.ROWS, state.getRows());
		values.put(SearchLiteGraphStateKeys.RESULT_SUMMARY, state.getResultSummary());
		values.put(SearchLiteGraphStateKeys.ERROR, state.getError());
		return values;
	}

}
