package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

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
	}

}
