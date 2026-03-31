package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentRecallMetadataResolverTest {

	private final DocumentRecallMetadataResolver resolver = new DocumentRecallMetadataResolver();

	@Test
	void should_prefer_user_topic_for_high_spending_user_queries() {
		DocumentRecallMetadataResolver.DocumentRecallFilter filter = resolver.resolve("查询高消费用户");

		assertEquals(1, filter.topics().size());
		assertEquals("user", filter.topics().get(0));
		assertTrue(filter.tags().contains("consumption"));
		assertFalse(filter.tags().contains("sales"));
	}

}
