package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

public record EvalMetricsSummary(EvalMetricValue expectationPassRate, EvalMetricValue intentAccuracy,
		EvalMetricValue failureFallbackAccuracy, EvalMetricValue unexpectedSqlGenerationBlockRate,
		EvalMetricValue unexpectedSqlExecutionBlockRate, EvalMetricValue sqlReferenceAccuracy,
		EvalMetricValue resultSignatureAccuracy, EvalMetricValue schemaRecallHitRate,
		EvalMetricValue sqlGenerationRate, EvalMetricValue sqlExecutionSuccessRate, EvalMetricValue resultModeAccuracy,
		EvalMetricValue multiTurnFollowupAccuracy) {
}
