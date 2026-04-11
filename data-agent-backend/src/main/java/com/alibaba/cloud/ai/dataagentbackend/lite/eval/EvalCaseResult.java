package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import java.util.List;

public record EvalCaseResult(String caseId, String title, String datasetId, String category, String scenarioType,
		String query, String threadId, List<String> history, String intentClassification, List<String> recalledTables,
		List<String> recalledDocuments, List<String> recalledEvidences, String canonicalQuery, String contextualizedQuery,
		String sql, int sqlRetryCount, String resultMode, int rowCount, String summary, String error, long durationMs,
		Boolean intentMatched, Boolean schemaRecallHit, boolean sqlGenerated, boolean sqlExecuted,
		Boolean resultModeMatched, Boolean multiTurnFollowupMatched, boolean passed, List<String> failedChecks) {

	public EvalCaseResult {
		history = history == null ? List.of() : List.copyOf(history);
		recalledTables = recalledTables == null ? List.of() : List.copyOf(recalledTables);
		recalledDocuments = recalledDocuments == null ? List.of() : List.copyOf(recalledDocuments);
		recalledEvidences = recalledEvidences == null ? List.of() : List.copyOf(recalledEvidences);
		failedChecks = failedChecks == null ? List.of() : List.copyOf(failedChecks);
	}

}
