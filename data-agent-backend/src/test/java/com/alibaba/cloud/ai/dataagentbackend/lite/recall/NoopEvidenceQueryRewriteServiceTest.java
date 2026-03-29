package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class NoopEvidenceQueryRewriteServiceTest {

	@Test
	void should_return_original_query_trimmed() {
		NoopEvidenceQueryRewriteService service = new NoopEvidenceQueryRewriteService();
		assertEquals("查询销售额", service.rewrite("  查询销售额  "));
	}

}
