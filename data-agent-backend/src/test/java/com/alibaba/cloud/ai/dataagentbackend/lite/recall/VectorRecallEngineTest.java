package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding.EmbeddingClient;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class VectorRecallEngineTest {

	@Test
	void should_rank_by_cosine_similarity() {
		EmbeddingClient embeddingClient = text -> {
			if (text.contains("订单")) {
				return List.of(1.0, 0.0);
			}
			if (text.contains("用户")) {
				return List.of(0.0, 1.0);
			}
			return List.of(0.5, 0.5);
		};
		VectorRecallEngine engine = new VectorRecallEngine(embeddingClient);

		RecallDocument orders = RecallEmbeddings.withEmbedding(
				new RecallDocument("schema-table:orders", RecallDocumentType.SCHEMA_TABLE, "orders", "订单表",
						Map.of("tableName", "orders")),
				List.of(1.0, 0.0), "mock");
		RecallDocument users = RecallEmbeddings.withEmbedding(
				new RecallDocument("schema-table:users", RecallDocumentType.SCHEMA_TABLE, "users", "用户表",
						Map.of("tableName", "users")),
				List.of(0.0, 1.0), "mock");

		List<RecallHit> hits = engine.search("查询订单金额", List.of(orders, users),
				new RecallOptions(2, java.util.Set.of(RecallDocumentType.SCHEMA_TABLE), Map.of()));

		assertEquals(1, hits.size());
		assertEquals("schema-table:orders", hits.get(0).document().id());
	}

}
