package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class KeywordRecallEngineTest {

	private final KeywordRecallEngine engine = new KeywordRecallEngine();

	@Test
	void should_recall_schema_documents_by_query_tokens() {
		List<RecallDocument> docs = List.of(
				new RecallDocument("t1", RecallDocumentType.SCHEMA_TABLE, "orders", "订单表，包含订单状态和总金额", Map.of()),
				new RecallDocument("t2", RecallDocumentType.SCHEMA_TABLE, "users", "用户表，包含注册时间", Map.of()),
				new RecallDocument("e1", RecallDocumentType.EVIDENCE, "销售额口径", "销售额默认使用订单明细汇总", Map.of()));

		List<RecallHit> hits = engine.search("查询订单金额", docs,
				new RecallOptions(2, Set.of(RecallDocumentType.SCHEMA_TABLE), Map.of()));

		assertEquals(1, hits.size());
		assertEquals("t1", hits.get(0).document().id());
		assertFalse(hits.get(0).matchedTerms().isEmpty());
	}

	@Test
	void should_filter_documents_by_metadata() {
		List<RecallDocument> docs = List.of(
				new RecallDocument("c1", RecallDocumentType.SCHEMA_COLUMN, "orders.status", "订单状态",
						Map.of("tableName", "orders")),
				new RecallDocument("c2", RecallDocumentType.SCHEMA_COLUMN, "users.created_at", "用户注册时间",
						Map.of("tableName", "users")));

		List<RecallHit> hits = engine.search("状态", docs,
				new RecallOptions(5, Set.of(RecallDocumentType.SCHEMA_COLUMN), Map.of("tableName", "orders")));

		assertEquals(1, hits.size());
		assertEquals("c1", hits.get(0).document().id());
	}

	@Test
	void should_filter_documents_by_collection_metadata_overlap() {
		List<RecallDocument> docs = List.of(
				new RecallDocument("e1", RecallDocumentType.EVIDENCE, "销售额口径", "订单明细汇总",
						Map.of("topic", "sales", "tags", List.of("sales", "metric"))),
				new RecallDocument("e2", RecallDocumentType.EVIDENCE, "核心用户定义", "近30天支付用户",
						Map.of("topic", "user", "tags", List.of("user", "core-user"))));

		List<RecallHit> hits = engine.search("查询销售额", docs,
				new RecallOptions(5, Set.of(RecallDocumentType.EVIDENCE), Map.of("topic", List.of("sales", "order"))));

		assertEquals(1, hits.size());
		assertEquals("e1", hits.get(0).document().id());
	}

}
