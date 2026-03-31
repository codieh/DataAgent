package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding.EmbeddingClient;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HybridRecallEngineTest {

	@Test
	void should_boost_schema_table_with_exact_match_and_type_weight() {
		EmbeddingClient embeddingClient = text -> List.of(0.5, 0.5);
		HybridRecallEngine engine = new HybridRecallEngine(embeddingClient, "hybrid", 0.5, 1.2, 1.0, 0.8, 0.9, 0.2);

		RecallDocument table = RecallEmbeddings.withEmbedding(
				new RecallDocument("schema-table:orders", RecallDocumentType.SCHEMA_TABLE, "orders", "订单表",
						Map.of("tableName", "orders")),
				List.of(1.0, 0.0), "mock");
		RecallDocument evidence = RecallEmbeddings.withEmbedding(
				new RecallDocument("evidence:orders", RecallDocumentType.EVIDENCE, "订单说明", "订单统计规则",
						Map.of("topic", "order")),
				List.of(1.0, 0.0), "mock");

		List<RecallHit> hits = engine.search("orders 订单查询", List.of(table, evidence),
				new RecallOptions(2, Set.of(), Map.of()));

		assertEquals(2, hits.size());
		assertEquals("schema-table:orders", hits.get(0).document().id());
		assertTrue(((Number) hits.get(0).document().metadata().get("_typeWeight")).doubleValue() > 1.0);
		assertTrue(((Number) hits.get(0).document().metadata().get("_exactMatchBonus")).doubleValue() > 0);
	}

	@Test
	void should_normalize_keyword_score_before_fusion() {
		EmbeddingClient embeddingClient = text -> List.of(1.0, 0.0);
		HybridRecallEngine engine = new HybridRecallEngine(embeddingClient, "hybrid", 0.5, 1.0, 1.0, 1.0, 0.9, 0.0);

		RecallDocument strongKeyword = RecallEmbeddings.withEmbedding(
				new RecallDocument("d1", RecallDocumentType.EVIDENCE, "订单金额", "订单金额 订单金额 订单金额", Map.of()),
				List.of(1.0, 0.0), "mock");
		RecallDocument weakKeyword = RecallEmbeddings.withEmbedding(
				new RecallDocument("d2", RecallDocumentType.EVIDENCE, "订单", "订单", Map.of()),
				List.of(1.0, 0.0), "mock");

		List<RecallHit> hits = engine.search("订单金额", List.of(strongKeyword, weakKeyword),
				new RecallOptions(2, Set.of(), Map.of()));

		assertEquals(2, hits.size());
		assertTrue(((Number) hits.get(0).document().metadata().get("_keywordNormalized")).doubleValue() <= 1.0);
		assertTrue(((Number) hits.get(1).document().metadata().get("_keywordNormalized")).doubleValue() <= 1.0);
	}

}
