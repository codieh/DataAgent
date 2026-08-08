package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import java.util.List;

public record EvalCaseResult(String caseId, String title, String datasetId, String category, String scenarioType,
		String query, String threadId, List<String> history, String intentClassification, List<String> recalledTables,
		List<String> recalledDocuments, List<String> recalledEvidences, String canonicalQuery, String contextualizedQuery,
		String sql, int sqlRetryCount, String resultMode, int rowCount, String summary, String error, long durationMs,
		boolean plannerEnabled, String plannerDecision, int planStepCount, boolean planFinished, String planFinishedReason,
		Boolean intentMatched, Boolean schemaRecallHit, boolean sqlGenerated, boolean sqlExecuted,
		boolean unexpectedSqlGeneration, boolean unexpectedSqlExecution, Boolean sqlReferenceMatched,
		Boolean resultSignatureMatched, Boolean resultModeMatched, Boolean multiTurnFollowupMatched,
		Boolean plannerEnabledMatched, Boolean plannerDecisionMatched, Boolean plannerStepCountMatched,
		Boolean plannerStepInstructionsMatched, Boolean planFinishedMatched, Boolean planFinishedReasonMatched,
		Boolean plannerMatched, String diagnosticStatus, String primaryFailure, boolean goalPassed, boolean strictPassed,
		boolean passed, List<String> goalFailures, List<String> failedChecks) {

	public EvalCaseResult {
		history = history == null ? List.of() : List.copyOf(history);
		recalledTables = recalledTables == null ? List.of() : List.copyOf(recalledTables);
		recalledDocuments = recalledDocuments == null ? List.of() : List.copyOf(recalledDocuments);
		recalledEvidences = recalledEvidences == null ? List.of() : List.copyOf(recalledEvidences);
		plannerDecision = plannerDecision == null ? "" : plannerDecision;
		planFinishedReason = planFinishedReason == null ? "" : planFinishedReason;
		diagnosticStatus = diagnosticStatus == null || diagnosticStatus.isBlank() ? "unknown" : diagnosticStatus;
		primaryFailure = primaryFailure == null ? "" : primaryFailure;
		goalFailures = goalFailures == null ? List.of() : List.copyOf(goalFailures);
		failedChecks = failedChecks == null ? List.of() : List.copyOf(failedChecks);
	}

}
