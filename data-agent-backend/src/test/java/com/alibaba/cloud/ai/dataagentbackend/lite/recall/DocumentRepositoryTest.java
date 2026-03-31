package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DocumentRepositoryTest {

	@Test
	void should_load_supported_documents_from_directory() throws Exception {
		Path dir = Files.createTempDirectory("document-repo");
		Files.createDirectories(dir.resolve("metrics"));
		Files.writeString(dir.resolve("metrics").resolve("gmv.md"), "# GMV\nGMV 默认按订单明细汇总");
		Files.writeString(dir.resolve("faq.txt"), "销售额默认不含取消订单");
		Files.writeString(dir.resolve("ignore.csv"), "a,b,c");

		DocumentRepository repository = new DocumentRepository(dir.toString());
		List<DocumentIndexBuilder.SourceDocument> documents = repository.listAll();

		assertEquals(2, documents.size());
		assertEquals(Set.of("gmv", "faq"), documents.stream().map(DocumentIndexBuilder.SourceDocument::docName).collect(java.util.stream.Collectors.toSet()));
	}

}
