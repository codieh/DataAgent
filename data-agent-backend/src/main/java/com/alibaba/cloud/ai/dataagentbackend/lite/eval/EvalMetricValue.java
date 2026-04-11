package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

public record EvalMetricValue(int passed, int total, double rate) {

	public static EvalMetricValue of(int passed, int total) {
		double rate = total == 0 ? 0.0d : (double) passed / (double) total;
		return new EvalMetricValue(passed, total, rate);
	}

}
