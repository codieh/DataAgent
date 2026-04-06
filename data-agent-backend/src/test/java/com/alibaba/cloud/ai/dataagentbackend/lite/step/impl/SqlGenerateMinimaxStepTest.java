package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class SqlGenerateMinimaxStepTest {

	@Test
	void prompt_should_make_schema_authoritative_and_split_evidence_from_documents() {
		String prompt = SqlGenerateMinimaxStep.buildSqlGenerationPrompt("统计每个分类的销售额", "TABLE orders ...",
				"[证据1] 销售额按订单明细汇总", "[定义1] GMV 默认按已支付订单汇总", 200);

		assertTrue(prompt.contains("Authoritative database schema"));
		assertTrue(prompt.contains("Supporting business rules and FAQ hints"));
		assertTrue(prompt.contains("Supporting definitions and background documents"));
		assertTrue(prompt.contains("If evidence conflicts with schema, always trust schema."));
		assertTrue(prompt.contains("If documents conflict with schema, always trust schema."));
		assertTrue(prompt.contains("If a document provides a definition that clearly matches the user question"));
		assertTrue(prompt.contains("If evidence or documents are irrelevant to the current question, ignore them."));
		assertTrue(prompt.contains("Use ONLY tables/columns that exist in the schema section."));
	}

}
