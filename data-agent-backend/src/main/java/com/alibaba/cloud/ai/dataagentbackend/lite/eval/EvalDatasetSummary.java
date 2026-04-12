package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

public record EvalDatasetSummary(String datasetId, String suite, int totalCases, int passedCases, int failedCases,
		long averageDurationMs) {
}
