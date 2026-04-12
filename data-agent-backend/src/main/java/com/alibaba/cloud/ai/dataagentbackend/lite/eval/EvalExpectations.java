package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import java.util.List;

public record EvalExpectations(String expectedIntent, List<String> expectedTables, String expectedResultMode,
		Boolean expectedSqlGenerated, Boolean expectedSqlExecuted, Integer expectedSqlRetryCount,
		List<String> expectedContextualizedQueryContains, String referenceSql, List<String> expectedSqlContains,
		Integer expectedRowCount, List<String> expectedSummaryContains) {

	public EvalExpectations {
		expectedTables = expectedTables == null ? List.of() : List.copyOf(expectedTables);
		expectedContextualizedQueryContains = expectedContextualizedQueryContains == null ? List.of()
				: List.copyOf(expectedContextualizedQueryContains);
		referenceSql = referenceSql == null ? "" : referenceSql;
		expectedSqlContains = expectedSqlContains == null ? List.of() : List.copyOf(expectedSqlContains);
		expectedSummaryContains = expectedSummaryContains == null ? List.of() : List.copyOf(expectedSummaryContains);
	}

}
