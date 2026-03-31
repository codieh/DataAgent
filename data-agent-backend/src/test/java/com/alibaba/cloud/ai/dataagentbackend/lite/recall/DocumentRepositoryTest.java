package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentRepositoryTest {

	@Test
	void should_load_supported_documents_and_chunk_markdown() throws Exception {
		Path dir = Files.createTempDirectory("document-repo");
		Files.createDirectories(dir.resolve("metrics"));
		Files.writeString(dir.resolve("metrics").resolve("gmv.md"), """
				# GMV
				GMV 默认按订单明细汇总。

				## 取消订单
				取消订单不计入销售额。
				""");
		Files.writeString(dir.resolve("faq.txt"), "销售额默认不含取消订单");
		Files.writeString(dir.resolve("ignore.csv"), "a,b,c");

		DocumentRepository repository = new DocumentRepository(dir.toString(), new DocumentChunker(120));
		List<DocumentIndexBuilder.SourceDocument> documents = repository.listAll();

		assertEquals(3, documents.size());
		assertEquals(Set.of("gmv", "faq"), documents.stream()
			.map(DocumentIndexBuilder.SourceDocument::docName)
			.collect(Collectors.toSet()));
		assertTrue(documents.stream().anyMatch(doc -> doc.sectionTitle().equals("GMV")));
		assertTrue(documents.stream().anyMatch(doc -> doc.sectionTitle().equals("取消订单")));
	}

}
