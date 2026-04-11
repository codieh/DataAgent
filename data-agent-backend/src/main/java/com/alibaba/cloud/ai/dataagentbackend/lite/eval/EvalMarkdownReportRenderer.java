package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import org.springframework.stereotype.Component;

import java.util.List;
import java.util.stream.Collectors;

@Component
public class EvalMarkdownReportRenderer {

	public String render(EvalRunReport report) {
		StringBuilder builder = new StringBuilder();
		builder.append("# Lite Eval Report\n\n");
		builder.append("- Report ID: ").append(report.reportId()).append("\n");
		builder.append("- Generated At: ").append(report.generatedAt()).append("\n");
		builder.append("- Total Cases: ").append(report.totalCases()).append("\n");
		builder.append("- Passed Cases: ").append(report.passedCases()).append("\n");
		builder.append("- Failed Cases: ").append(report.failedCases()).append("\n\n");

		builder.append("## Datasets\n\n");
		for (String datasetFile : report.datasetFiles()) {
			builder.append("- ").append(datasetFile).append("\n");
		}
		builder.append("\n");

		builder.append("## Metrics\n\n");
		builder.append("| Metric | Passed | Total | Rate |\n");
		builder.append("| --- | ---: | ---: | ---: |\n");
		appendMetric(builder, "Intent Accuracy", report.metrics().intentAccuracy());
		appendMetric(builder, "Schema Recall Hit Rate", report.metrics().schemaRecallHitRate());
		appendMetric(builder, "SQL Generation Rate", report.metrics().sqlGenerationRate());
		appendMetric(builder, "SQL Execution Success Rate", report.metrics().sqlExecutionSuccessRate());
		appendMetric(builder, "Result Mode Accuracy", report.metrics().resultModeAccuracy());
		appendMetric(builder, "Multi-turn Follow-up Accuracy", report.metrics().multiTurnFollowupAccuracy());
		builder.append("\n");

		List<EvalCaseResult> failedCases = report.results().stream().filter(result -> !result.passed()).toList();
		builder.append("## Failed Cases\n\n");
		if (failedCases.isEmpty()) {
			builder.append("No failed cases.\n\n");
		}
		else {
			builder.append("| Case ID | Scenario | Query | Failed Checks | Actual Result Mode | Error |\n");
			builder.append("| --- | --- | --- | --- | --- | --- |\n");
			for (EvalCaseResult result : failedCases) {
				builder.append("| ").append(result.caseId()).append(" | ").append(result.scenarioType()).append(" | ")
					.append(escapeCell(result.query())).append(" | ")
					.append(escapeCell(String.join(", ", result.failedChecks()))).append(" | ")
					.append(escapeCell(result.resultMode())).append(" | ").append(escapeCell(result.error())).append(" |\n");
			}
			builder.append("\n");
		}

		builder.append("## Case Summary\n\n");
		builder.append("| Case ID | Category | Scenario | Passed | Intent | Recalled Tables | Result Mode | SQL Retry | Duration(ms) |\n");
		builder.append("| --- | --- | --- | ---: | --- | --- | --- | ---: | ---: |\n");
		for (EvalCaseResult result : report.results()) {
			builder.append("| ").append(result.caseId()).append(" | ").append(escapeCell(result.category())).append(" | ")
				.append(result.scenarioType()).append(" | ").append(result.passed() ? "Y" : "N").append(" | ")
				.append(escapeCell(result.intentClassification())).append(" | ")
				.append(escapeCell(String.join(", ", result.recalledTables()))).append(" | ")
				.append(escapeCell(result.resultMode())).append(" | ").append(result.sqlRetryCount()).append(" | ")
				.append(result.durationMs()).append(" |\n");
		}
		return builder.toString();
	}

	private void appendMetric(StringBuilder builder, String name, EvalMetricValue value) {
		builder.append("| ").append(name).append(" | ").append(value.passed()).append(" | ").append(value.total()).append(" | ")
			.append(String.format("%.2f%%", value.rate() * 100.0d)).append(" |\n");
	}

	private String escapeCell(String value) {
		if (value == null) {
			return "";
		}
		return value.replace("\r", " ").replace("\n", "<br>").replace("|", "\\|");
	}

}
