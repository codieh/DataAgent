package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class SqlGenerateMinimaxStepTest {

	@Test
	void prompt_should_make_schema_authoritative_and_evidence_optional() {
		String prompt = SqlGenerateMinimaxStep.buildSqlGenerationPrompt("统计每个分类的销售额", "TABLE orders ...",
				"[证据1] 销售额按订单明细汇总", 200);

		assertTrue(prompt.contains("Authoritative database schema"));
		assertTrue(prompt.contains("Supporting business evidence"));
		assertTrue(prompt.contains("If evidence conflicts with schema, always trust schema."));
		assertTrue(prompt.contains("If evidence is irrelevant, ignore it."));
		assertTrue(prompt.contains("Use ONLY tables/columns that exist in the schema section."));
	}

}
