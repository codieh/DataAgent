package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.graph.OverAllState;

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
		values.put(SearchLiteGraphStateKeys.SQL, state.getSql());
		values.put(SearchLiteGraphStateKeys.ROWS, state.getRows());
		values.put(SearchLiteGraphStateKeys.RESULT_SUMMARY, state.getResultSummary());
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
		state.setSchemaTableDetails(get(graphState, SearchLiteGraphStateKeys.SCHEMA_TABLE_DETAILS, java.util.List.class));
		state.setRecalledTables(get(graphState, SearchLiteGraphStateKeys.RECALLED_TABLES, java.util.List.class));
		state.setRecalledSchemaText(get(graphState, SearchLiteGraphStateKeys.RECALLED_SCHEMA_TEXT, String.class));
		state.setCanonicalQuery(get(graphState, SearchLiteGraphStateKeys.CANONICAL_QUERY, String.class));
		state.setExpandedQueries(get(graphState, SearchLiteGraphStateKeys.EXPANDED_QUERIES, java.util.List.class));
		state.setSql(get(graphState, SearchLiteGraphStateKeys.SQL, String.class));
		state.setRows(get(graphState, SearchLiteGraphStateKeys.ROWS, java.util.List.class));
		state.setResultSummary(get(graphState, SearchLiteGraphStateKeys.RESULT_SUMMARY, String.class));
		state.setError(get(graphState, SearchLiteGraphStateKeys.ERROR, String.class));
		return state;
	}

	@SuppressWarnings("unchecked")
	private static <T> T get(OverAllState graphState, String key, Class<?> type) {
		return (T) graphState.value(key).filter(type::isInstance).orElse(null);
	}

}
