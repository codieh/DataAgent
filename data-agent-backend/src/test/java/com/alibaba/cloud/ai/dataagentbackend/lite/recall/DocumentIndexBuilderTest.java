package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentIndexBuilderTest {

	private final DocumentIndexBuilder builder = new DocumentIndexBuilder();

	@Test
	void should_convert_source_documents_to_document_recall_type() {
		List<DocumentIndexBuilder.SourceDocument> sourceDocuments = List.of(
				new DocumentIndexBuilder.SourceDocument("document:metrics/gmv.md", "gmv", "GMV 定义", 0,
						Path.of("metrics", "gmv.md"), "md", "GMV 默认按订单明细汇总"));

		List<RecallDocument> documents = builder.build(sourceDocuments);

		assertEquals(1, documents.size());
		assertEquals(RecallDocumentType.DOCUMENT, documents.get(0).type());
		assertEquals("gmv / GMV 定义", documents.get(0).title());
		assertEquals("document", documents.get(0).metadata().get("sourceType"));
		assertEquals("sales", documents.get(0).metadata().get("topic"));
	}

	@Test
	void should_not_mark_rule_chunk_as_user_topic_only_because_it_mentions_user_phrase() {
		List<DocumentIndexBuilder.SourceDocument> sourceDocuments = List.of(
				new DocumentIndexBuilder.SourceDocument("document:rules/inventory-and-sales.txt#3", "inventory-and-sales",
						"inventory-and-sales", 3, Path.of("business-rules", "inventory-and-sales.txt"), "txt",
						"如果用户询问“最畅销商品”“销量最高商品”，优先按销量 descending 排序。"));

		List<RecallDocument> documents = builder.build(sourceDocuments);

		assertEquals(1, documents.size());
		assertTrue(!"user".equals(documents.get(0).metadata().get("topic")));
		assertTrue(((List<?>) documents.get(0).metadata().get("tags")).contains("rule"));
	}

}
