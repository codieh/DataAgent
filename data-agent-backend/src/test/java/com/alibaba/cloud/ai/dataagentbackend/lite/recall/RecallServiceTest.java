package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaColumn;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaForeignKey;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding.EmbeddingClient;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding.EmbeddingProperties;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.store.FileRecallDocumentStore;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RecallServiceTest {

	@Test
	void should_recall_evidence_items() throws Exception {
		RecallService recallService = new RecallService(new KeywordRecallEngine(), new EvidenceIndexBuilder(),
				new DocumentIndexBuilder(),
				new SchemaIndexBuilder(),
				new FileRecallDocumentStore(new ObjectMapper(), Files.createTempDirectory("recall-service-evidence").toString()),
				new RecallEmbeddingService(noopEmbeddingClient(), new EmbeddingProperties("http://localhost", "", "bge-m3", "/v1/embeddings"),
						"keyword"),
				new EvidenceRecallMetadataResolver(),
				new DocumentRecallMetadataResolver());

		List<EvidenceItem> items = List.of(
				new EvidenceItem("e1", "销售额口径", "销售额默认按订单明细汇总", "mock://sales", 0.9,
						Map.of("type", "RULE", "tags", List.of("metric", "sales"))),
				new EvidenceItem("e2", "核心用户定义", "近 30 天完成过支付且退款率 < 5% 的用户", "mock://user", 0.8,
						Map.of("type", "FAQ", "tags", List.of("user", "core-user"))));

		EvidenceRecallResult result = recallService.recallEvidence("查询销售额", items, 5);

		assertEquals(1, result.items().size());
		assertEquals("e1", result.items().get(0).id());
		assertTrue(result.promptText().contains("销售额"));
	}

	@Test
	void should_recall_schema_tables() throws Exception {
		RecallService recallService = new RecallService(new KeywordRecallEngine(), new EvidenceIndexBuilder(),
				new DocumentIndexBuilder(),
				new SchemaIndexBuilder(),
				new FileRecallDocumentStore(new ObjectMapper(), Files.createTempDirectory("recall-service-schema").toString()),
				new RecallEmbeddingService(noopEmbeddingClient(), new EmbeddingProperties("http://localhost", "", "bge-m3", "/v1/embeddings"),
						"keyword"),
				new EvidenceRecallMetadataResolver(),
				new DocumentRecallMetadataResolver());

		List<SchemaTable> tables = List.of(
				new SchemaTable("orders", "订单表",
						List.of(new SchemaColumn("total_amount", "decimal", "decimal(10,2)", true, false, "订单总金额")),
						List.of(new SchemaForeignKey("user_id", "users", "id"))),
				new SchemaTable("users", "用户表",
						List.of(new SchemaColumn("created_at", "datetime", "datetime", false, false, "注册时间")),
						List.of()));

		SchemaRecallResult result = recallService.recallSchema("查询订单金额", "", tables, 3);

		assertFalse(result.tables().isEmpty());
		assertEquals("orders", result.tables().get(0).name());
		assertTrue(result.promptText().contains("TABLE orders"));
		assertTrue(result.promptText().contains("total_amount"));
		assertFalse(result.promptText().contains("created_at"));
		assertFalse(result.focusedTables().isEmpty());
		assertEquals("orders", result.focusedTables().get(0).name());
	}

	@Test
	void should_recall_document_chunks() throws Exception {
		RecallService recallService = new RecallService(new KeywordRecallEngine(), new EvidenceIndexBuilder(),
				new DocumentIndexBuilder(), new SchemaIndexBuilder(),
				new FileRecallDocumentStore(new ObjectMapper(), Files.createTempDirectory("recall-service-document").toString()),
				new RecallEmbeddingService(noopEmbeddingClient(), new EmbeddingProperties("http://localhost", "", "bge-m3", "/v1/embeddings"),
						"keyword"),
				new EvidenceRecallMetadataResolver(),
				new DocumentRecallMetadataResolver());

		List<DocumentIndexBuilder.SourceDocument> sourceDocuments = List.of(
				new DocumentIndexBuilder.SourceDocument("document:metrics/gmv.md#0", "gmv", "GMV 定义", 0,
						java.nio.file.Path.of("metrics", "gmv.md"), "md", "GMV 默认按订单明细汇总，取消订单不计入销售额"),
				new DocumentIndexBuilder.SourceDocument("document:faq/user.txt#0", "user", "用户说明", 0,
						java.nio.file.Path.of("faq", "user.txt"), "txt", "高消费用户通常指消费金额排名靠前的用户"),
				new DocumentIndexBuilder.SourceDocument("document:rules/inventory.txt#0", "inventory", "库存规则", 0,
						java.nio.file.Path.of("rules", "inventory.txt"), "txt", "低库存商品通常指 stock 小于 20"));

		DocumentRecallResult result = recallService.recallDocuments("查询高消费用户", sourceDocuments, 3);

		assertEquals(1, result.documents().size());
		assertEquals(RecallDocumentType.DOCUMENT, result.documents().get(0).type());
		assertTrue(result.promptText().contains("高消费用户"));
	}

	private static EmbeddingClient noopEmbeddingClient() {
		return text -> List.of();
	}

}
