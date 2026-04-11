package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
		"spring.datasource.url=jdbc:h2:mem:evaldb;MODE=MySQL;DB_CLOSE_DELAY=-1;DATABASE_TO_LOWER=true",
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
		"search.lite.eval.cases-dir=D:/GitHub/DataAgent/data-agent-backend/data/eval/cases",
		"search.lite.eval.reports-dir=D:/GitHub/DataAgent/data-agent-backend/target/test-eval-reports",
		"APP_LOG_LEVEL=INFO"
})
class EvalRunnerTest {

	@Autowired
	private EvalRunner evalRunner;

	@MockBean
	private SearchLiteGraphService searchLiteGraphService;

	@Test
	void runDefaultSuite_should_generate_json_and_markdown_reports() throws Exception {
		EvalRunReport report = evalRunner.runDefaultSuite();

		assertNotNull(report);
		assertEquals(17, report.totalCases());
		assertNotNull(report.metrics());
		assertFalse(report.results().isEmpty());

		Path latestJson = Path.of("D:/GitHub/DataAgent/data-agent-backend/target/test-eval-reports/latest-report.json");
		Path latestMd = Path.of("D:/GitHub/DataAgent/data-agent-backend/target/test-eval-reports/latest-report.md");

		assertTrue(Files.exists(latestJson));
		assertTrue(Files.exists(latestMd));
		assertTrue(Files.size(latestJson) > 0L);
		assertTrue(Files.size(latestMd) > 0L);
		assertTrue(report.results().stream().anyMatch(result -> "multi_turn".equalsIgnoreCase(result.scenarioType())));
	}

}
