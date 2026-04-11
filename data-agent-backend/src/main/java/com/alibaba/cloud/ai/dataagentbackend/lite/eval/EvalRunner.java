package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteRequest;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteOrchestrator;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteRunResult;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.io.IOException;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

@Service
public class EvalRunner {

	private static final DateTimeFormatter REPORT_ID_FORMAT = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
		.withLocale(Locale.ROOT)
		.withZone(ZoneId.systemDefault());

	private final SearchLiteOrchestrator orchestrator;

	private final EvalCaseLoader caseLoader;

	private final EvalReportWriter reportWriter;

	private final String defaultAgentId;

	public EvalRunner(SearchLiteOrchestrator orchestrator, EvalCaseLoader caseLoader, EvalReportWriter reportWriter,
			@Value("${search.lite.eval.agent-id:eval-agent}") String defaultAgentId) {
		this.orchestrator = orchestrator;
		this.caseLoader = caseLoader;
		this.reportWriter = reportWriter;
		this.defaultAgentId = defaultAgentId;
	}

	public EvalRunReport runDefaultSuite() throws IOException {
		List<EvalCaseLoader.LoadedEvalDataset> loadedDatasets = caseLoader.loadAll();
		List<EvalCaseResult> results = new ArrayList<>();
		for (EvalCaseLoader.LoadedEvalDataset loadedDataset : loadedDatasets) {
			for (EvalCaseDefinition definition : loadedDataset.dataset().cases()) {
				results.add(runCase(loadedDataset.dataset().datasetId(), definition));
			}
		}

		EvalRunReport report = buildReport(loadedDatasets, results);
		reportWriter.write(report);
		return report;
	}

	private EvalCaseResult runCase(String datasetId, EvalCaseDefinition definition) {
		String agentId = StringUtils.hasText(definition.agentId()) ? definition.agentId().trim() : defaultAgentId;
		String threadId = "eval-" + definition.caseId().toLowerCase(Locale.ROOT) + "-" + UUID.randomUUID();
		long startedAt = System.nanoTime();

		for (EvalHistoryTurn historyTurn : definition.history()) {
			orchestrator.runForEvaluation(new SearchLiteRequest(agentId, threadId, historyTurn.query())).block();
		}

		SearchLiteRunResult runResult = orchestrator
			.runForEvaluation(new SearchLiteRequest(agentId, threadId, definition.query()))
			.block();

		long durationMs = runResult == null ? 0L : runResult.durationMs();
		if (durationMs <= 0L) {
			durationMs = (System.nanoTime() - startedAt) / 1_000_000L;
		}

		SearchLiteState state = runResult == null ? new SearchLiteState() : runResult.state();
		List<SearchLiteMessage> messages = runResult == null ? List.of() : runResult.messages();
		EvalExpectations expectations = definition.expectations();
		boolean sqlGenerated = StringUtils.hasText(state.getSql());
		boolean sqlExecuted = sqlGenerated && !StringUtils.hasText(state.getError())
				&& !"execution_error".equalsIgnoreCase(state.getResultMode());

		Boolean intentMatched = hasExpectation(expectations.expectedIntent())
				? expectations.expectedIntent().equalsIgnoreCase(state.getIntentClassification()) : null;
		Boolean schemaRecallHit = expectations.expectedTables().isEmpty() ? null
				: containsAllIgnoreCase(state.getRecalledTables(), expectations.expectedTables());
		Boolean resultModeMatched = hasExpectation(expectations.expectedResultMode())
				? expectations.expectedResultMode().equalsIgnoreCase(state.getResultMode()) : null;
		Boolean multiTurnFollowupMatched = expectations.expectedContextualizedQueryContains().isEmpty() ? null
				: containsAllSnippets(state.getContextualizedQuery(), expectations.expectedContextualizedQueryContains());

		List<String> failedChecks = new ArrayList<>();
		addFailure(failedChecks, "intent", intentMatched);
		addFailure(failedChecks, "schema_recall", schemaRecallHit);
		addFailure(failedChecks, "result_mode", resultModeMatched);
		addFailure(failedChecks, "multi_turn_followup", multiTurnFollowupMatched);
		if (expectations.expectedSqlGenerated() != null && expectations.expectedSqlGenerated() != sqlGenerated) {
			failedChecks.add("sql_generated");
		}
		if (expectations.expectedSqlExecuted() != null && expectations.expectedSqlExecuted() != sqlExecuted) {
			failedChecks.add("sql_executed");
		}
		if (expectations.expectedSqlRetryCount() != null && expectations.expectedSqlRetryCount() != state.getSqlRetryCount()) {
			failedChecks.add("sql_retry_count");
		}

		return new EvalCaseResult(definition.caseId(), definition.title(), datasetId, definition.category(),
				definition.scenarioType(), definition.query(), threadId,
				definition.history().stream().map(EvalHistoryTurn::query).toList(), state.getIntentClassification(),
				copyList(state.getRecalledTables()), extractDocumentSummaries(messages),
				state.getEvidences().stream().map(EvidenceItem::title).toList(), state.getCanonicalQuery(),
				state.getContextualizedQuery(), state.getSql(), state.getSqlRetryCount(), state.getResultMode(),
				state.getRows() == null ? 0 : state.getRows().size(), state.getResultSummary(), state.getError(), durationMs,
				intentMatched, schemaRecallHit, sqlGenerated, sqlExecuted, resultModeMatched, multiTurnFollowupMatched,
				failedChecks.isEmpty(), failedChecks);
	}

	private EvalRunReport buildReport(List<EvalCaseLoader.LoadedEvalDataset> loadedDatasets, List<EvalCaseResult> results) {
		int passedCases = (int) results.stream().filter(EvalCaseResult::passed).count();
		int failedCases = results.size() - passedCases;
		EvalMetricsSummary metrics = new EvalMetricsSummary(
				metric(results, EvalCaseResult::intentMatched),
				metric(results, EvalCaseResult::schemaRecallHit),
				EvalMetricValue.of((int) results.stream().filter(EvalCaseResult::sqlGenerated).count(), results.size()),
				EvalMetricValue.of((int) results.stream().filter(EvalCaseResult::sqlExecuted).count(), results.size()),
				metric(results, EvalCaseResult::resultModeMatched),
				metric(results.stream()
					.filter(result -> "multi_turn".equalsIgnoreCase(result.scenarioType()))
					.toList(), EvalCaseResult::multiTurnFollowupMatched));
		return new EvalRunReport("eval-v1-" + REPORT_ID_FORMAT.format(Instant.now()), Instant.now(),
				loadedDatasets.stream().map(loaded -> loaded.path().toString()).toList(), results.size(), passedCases,
				failedCases, metrics, results);
	}

	private EvalMetricValue metric(List<EvalCaseResult> results,
			java.util.function.Function<EvalCaseResult, Boolean> extractor) {
		int total = 0;
		int passed = 0;
		for (EvalCaseResult result : results) {
			Boolean value = extractor.apply(result);
			if (value == null) {
				continue;
			}
			total++;
			if (Boolean.TRUE.equals(value)) {
				passed++;
			}
		}
		return EvalMetricValue.of(passed, total);
	}

	private boolean containsAllIgnoreCase(List<String> actual, List<String> expected) {
		LinkedHashSet<String> normalizedActual = new LinkedHashSet<>();
		for (String item : actual == null ? List.<String>of() : actual) {
			if (StringUtils.hasText(item)) {
				normalizedActual.add(item.trim().toLowerCase(Locale.ROOT));
			}
		}
		for (String expectedItem : expected) {
			if (!StringUtils.hasText(expectedItem)) {
				continue;
			}
			if (!normalizedActual.contains(expectedItem.trim().toLowerCase(Locale.ROOT))) {
				return false;
			}
		}
		return true;
	}

	private boolean containsAllSnippets(String actualText, List<String> expectedSnippets) {
		String normalized = actualText == null ? "" : actualText;
		for (String snippet : expectedSnippets) {
			if (!StringUtils.hasText(snippet)) {
				continue;
			}
			if (!normalized.contains(snippet)) {
				return false;
			}
		}
		return true;
	}

	private boolean hasExpectation(String value) {
		return StringUtils.hasText(value);
	}

	private void addFailure(List<String> failedChecks, String label, Boolean matched) {
		if (matched != null && !matched) {
			failedChecks.add(label);
		}
	}

	private List<String> extractDocumentSummaries(List<SearchLiteMessage> messages) {
		for (SearchLiteMessage message : messages) {
			if (message == null || message.stage() != SearchLiteStage.EVIDENCE || !(message.payload() instanceof Map<?, ?> payload)) {
				continue;
			}
			Object rawDocuments = payload.get("documents");
			if (!(rawDocuments instanceof List<?> documents)) {
				continue;
			}
			return documents.stream().map(this::toDocumentSummary).filter(StringUtils::hasText).toList();
		}
		return List.of();
	}

	private String toDocumentSummary(Object item) {
		if (!(item instanceof Map<?, ?> map)) {
			return "";
		}
		String title = valueToString(map.get("title"));
		String sectionTitle = valueToString(map.get("sectionTitle"));
		if (StringUtils.hasText(title) && StringUtils.hasText(sectionTitle)) {
			return title + " / " + sectionTitle;
		}
		return StringUtils.hasText(title) ? title : valueToString(map.get("id"));
	}

	private String valueToString(Object value) {
		return value == null ? "" : String.valueOf(value);
	}

	private List<String> copyList(List<String> values) {
		return values == null ? List.of() : List.copyOf(values);
	}

}
