package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import java.util.List;

public record EvalExpectations(String expectedIntent, List<String> expectedTables, String expectedResultMode,
		Boolean expectedSqlGenerated, Boolean expectedSqlExecuted, Integer expectedSqlRetryCount,
		List<String> expectedContextualizedQueryContains, String referenceSql, List<String> expectedSqlContains,
		Integer expectedRowCount, List<String> expectedSummaryContains, Boolean expectedPlannerEnabled,
		String expectedPlannerDecision, Integer expectedMinPlanStepCount, Integer expectedMaxPlanStepCount,
		List<String> expectedPlanStepInstructionsContain, Boolean expectedPlanFinished, String expectedPlanFinishedReason,
		List<String> allowedResultModes, List<String> forbiddenSummaryContains, List<String> forbiddenOutputContains) {

	public EvalExpectations {
		expectedTables = expectedTables == null ? List.of() : List.copyOf(expectedTables);
		expectedContextualizedQueryContains = expectedContextualizedQueryContains == null ? List.of()
				: List.copyOf(expectedContextualizedQueryContains);
		referenceSql = referenceSql == null ? "" : referenceSql;
		expectedSqlContains = expectedSqlContains == null ? List.of() : List.copyOf(expectedSqlContains);
		expectedSummaryContains = expectedSummaryContains == null ? List.of() : List.copyOf(expectedSummaryContains);
		expectedPlanStepInstructionsContain = expectedPlanStepInstructionsContain == null ? List.of()
				: List.copyOf(expectedPlanStepInstructionsContain);
		allowedResultModes = allowedResultModes == null ? List.of() : List.copyOf(allowedResultModes);
		forbiddenSummaryContains = forbiddenSummaryContains == null ? List.of() : List.copyOf(forbiddenSummaryContains);
		forbiddenOutputContains = forbiddenOutputContains == null ? List.of() : List.copyOf(forbiddenOutputContains);
	}

}
