package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class Bm25RecallEngineTest {

	@Test
	void should_prioritize_title_and_frequency_matches() {
		Bm25RecallEngine engine = new Bm25RecallEngine(1.2, 0.75, 2.0);
		RecallDocument exact = new RecallDocument("schema-table:orders", RecallDocumentType.SCHEMA_TABLE, "orders", "订单表",
				Map.of("tableName", "orders"));
		RecallDocument weaker = new RecallDocument("document:trend", RecallDocumentType.DOCUMENT, "交易趋势", "订单 趋势", Map.of());

		List<RecallHit> hits = engine.search("orders 订单", List.of(weaker, exact), new RecallOptions(2, Set.of(), Map.of()));

		assertEquals(2, hits.size());
		assertEquals("schema-table:orders", hits.get(0).document().id());
		assertTrue(((Number) hits.get(0).document().metadata().get("_bm25Score")).doubleValue() > 0);
	}

}
