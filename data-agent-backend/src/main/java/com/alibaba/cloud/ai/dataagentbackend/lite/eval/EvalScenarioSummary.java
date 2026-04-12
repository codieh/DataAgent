package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

public record EvalScenarioSummary(String scenarioType, int totalCases, int passedCases, int failedCases,
		long averageDurationMs) {
}
