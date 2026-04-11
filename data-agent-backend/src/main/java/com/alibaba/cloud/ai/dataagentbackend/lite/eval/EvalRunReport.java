package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import java.time.Instant;
import java.util.List;

public record EvalRunReport(String reportId, Instant generatedAt, List<String> datasetFiles, int totalCases,
		int passedCases, int failedCases, EvalMetricsSummary metrics, List<EvalCaseResult> results) {

	public EvalRunReport {
		datasetFiles = datasetFiles == null ? List.of() : List.copyOf(datasetFiles);
		results = results == null ? List.of() : List.copyOf(results);
	}

}
