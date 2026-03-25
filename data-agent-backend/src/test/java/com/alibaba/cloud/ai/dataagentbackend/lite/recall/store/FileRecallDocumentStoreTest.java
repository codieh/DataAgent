package com.alibaba.cloud.ai.dataagentbackend.lite.recall.store;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaColumn;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocument;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocumentType;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;

class FileRecallDocumentStoreTest {

	@Test
	void should_save_and_load_evidence_documents() throws Exception {
		FileRecallDocumentStore store = new FileRecallDocumentStore(new ObjectMapper(),
				Files.createTempDirectory("file-recall-store-evidence").toString());

		List<RecallDocument> docs = List.of(
				new RecallDocument("e1", RecallDocumentType.EVIDENCE, "销售额口径", "销售额默认按订单明细统计",
						Map.of("source", "mock://sales")));

		store.saveEvidenceDocuments(docs);

		List<RecallDocument> loaded = store.loadEvidenceDocuments();
		assertEquals(1, loaded.size());
		assertEquals("e1", loaded.get(0).id());
	}

	@Test
	void should_save_and_load_schema_index() throws Exception {
		FileRecallDocumentStore store = new FileRecallDocumentStore(new ObjectMapper(),
				Files.createTempDirectory("file-recall-store-schema").toString());

		PersistedSchemaIndex schemaIndex = new PersistedSchemaIndex(
				List.of(new SchemaTable("orders", "订单表",
						List.of(new SchemaColumn("id", "int", "int", true, true, "主键")), List.of())),
				"TABLE orders", List.of(new RecallDocument("schema-table:orders", RecallDocumentType.SCHEMA_TABLE, "orders",
						"订单表", Map.of("tableName", "orders"))), List.of());

		store.saveSchemaIndex(schemaIndex);

		PersistedSchemaIndex loaded = store.loadSchemaIndex().orElseThrow();
		assertEquals(1, loaded.schemaTables().size());
		assertTrue(loaded.schemaText().contains("orders"));
	}

	@Test
	void should_report_store_status() throws Exception {
		FileRecallDocumentStore store = new FileRecallDocumentStore(new ObjectMapper(),
				Files.createTempDirectory("file-recall-store-status").toString());

		store.saveEvidenceDocuments(List.of(
				new RecallDocument("e1", RecallDocumentType.EVIDENCE, "销售额口径", "销售额默认按订单明细统计",
						Map.of("source", "mock://sales"))));

		RecallIndexStatus status = store.status();
		assertTrue(status.evidence().exists());
		assertEquals(1, status.evidence().count());
		assertFalse(status.schema().exists());
	}

}
