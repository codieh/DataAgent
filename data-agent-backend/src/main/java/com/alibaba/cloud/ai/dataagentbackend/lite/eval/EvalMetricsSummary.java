package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

public record EvalMetricsSummary(EvalMetricValue intentAccuracy, EvalMetricValue schemaRecallHitRate,
		EvalMetricValue sqlGenerationRate, EvalMetricValue sqlExecutionSuccessRate, EvalMetricValue resultModeAccuracy,
		EvalMetricValue multiTurnFollowupAccuracy) {
}
