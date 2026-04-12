package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
		"spring.datasource.url=jdbc:h2:mem:goldenevaldb;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=true",
		"spring.datasource.driver-class-name=org.h2.Driver",
		"spring.datasource.username=sa",
		"spring.datasource.password=",
		"search.lite.orchestrator.mode=pipeline",
		"search.lite.intent.provider=mock",
		"search.lite.evidence.provider=mock",
		"search.lite.schema.introspect.provider=mock",
		"search.lite.enhance.provider=mock",
		"search.lite.sql.generate.provider=mock",
		"search.lite.sql.execute.provider=mock",
		"search.lite.result.provider=mock",
		"search.lite.eval.suite=golden",
		"search.lite.eval.cases-dir=D:/GitHub/DataAgent/data-agent-backend/data/eval/cases",
		"search.lite.eval.reports-dir=D:/GitHub/DataAgent/data-agent-backend/target/test-eval-reports-golden",
		"APP_LOG_LEVEL=INFO"
})
class GoldenEvalRunnerTest {

	@Autowired
	private EvalRunner evalRunner;

	@MockBean
	private SearchLiteGraphService searchLiteGraphService;

	@Test
	void runGoldenSuite_should_only_load_curated_cases() throws Exception {
		EvalRunReport report = evalRunner.runDefaultSuite();

		assertNotNull(report);
		assertEquals("golden", report.suite());
		assertEquals(6, report.totalCases());
		assertEquals(1, report.datasetSummaries().size());
		assertEquals("golden-core-v1", report.datasetSummaries().get(0).datasetId());
		assertTrue(report.results().stream().allMatch(result -> result.caseId().startsWith("GC")));
		assertTrue(report.results().stream().anyMatch(result -> "failure_fallback".equalsIgnoreCase(result.scenarioType())));
		assertFalse(report.failureCheckCounts().isEmpty());
	}

}
