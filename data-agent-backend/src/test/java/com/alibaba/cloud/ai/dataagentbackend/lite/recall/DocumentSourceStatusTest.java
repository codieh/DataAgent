package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentSourceStatusTest {

	@Test
	void should_report_document_source_status() throws Exception {
		Path dir = Files.createTempDirectory("document-source-status");
		Files.createDirectories(dir.resolve("metrics"));
		Files.writeString(dir.resolve("metrics").resolve("gmv.md"), """
				# GMV
				GMV 默认按订单明细汇总。

				## 取消订单
				取消订单不计入销售额。
				""");

		DocumentRepository repository = new DocumentRepository(dir.toString(), new DocumentChunker(120));
		DocumentSourceStatus status = repository.status();

		assertTrue(status.exists());
		assertEquals(1, status.fileCount());
		assertEquals(2, status.chunkCount());
	}

}
