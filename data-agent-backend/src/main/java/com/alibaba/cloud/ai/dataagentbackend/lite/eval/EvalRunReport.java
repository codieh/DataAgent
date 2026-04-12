package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public record EvalRunReport(String reportId, Instant generatedAt, String suite, List<String> datasetFiles, int totalCases,
		int passedCases, int failedCases, long averageDurationMs, EvalMetricsSummary metrics,
		Map<String, Integer> statusCounts, Map<String, Integer> failureCheckCounts, List<EvalDatasetSummary> datasetSummaries,
		List<EvalScenarioSummary> scenarioSummaries, List<EvalCaseResult> results) {

	public EvalRunReport {
		suite = suite == null || suite.isBlank() ? "standard" : suite;
		datasetFiles = datasetFiles == null ? List.of() : List.copyOf(datasetFiles);
		statusCounts = statusCounts == null ? Map.of() : Map.copyOf(statusCounts);
		failureCheckCounts = failureCheckCounts == null ? Map.of() : Map.copyOf(failureCheckCounts);
		datasetSummaries = datasetSummaries == null ? List.of() : List.copyOf(datasetSummaries);
		scenarioSummaries = scenarioSummaries == null ? List.of() : List.copyOf(scenarioSummaries);
		results = results == null ? List.of() : List.copyOf(results);
	}

}
