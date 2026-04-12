package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import java.util.List;

public record EvalCaseDataset(String datasetId, String version, String suite, String description,
		List<EvalCaseDefinition> cases) {

	public EvalCaseDataset {
		cases = cases == null ? List.of() : List.copyOf(cases);
		suite = suite == null || suite.isBlank() ? "standard" : suite.trim().toLowerCase();
	}

}
