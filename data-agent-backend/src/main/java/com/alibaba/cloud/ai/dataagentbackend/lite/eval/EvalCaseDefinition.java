package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import java.util.List;

public record EvalCaseDefinition(String caseId, String title, String category, String scenarioType, String agentId,
		String query, List<EvalHistoryTurn> history, EvalExpectations expectations, List<String> tags, String notes) {

	public EvalCaseDefinition {
		history = history == null ? List.of() : List.copyOf(history);
		tags = tags == null ? List.of() : List.copyOf(tags);
		expectations = expectations == null
				? new EvalExpectations(null, List.of(), null, null, null, null, null, null, null, null, null)
				: expectations;
	}

}
