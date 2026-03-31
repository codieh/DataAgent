package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentChunkerTest {

	private final DocumentChunker chunker = new DocumentChunker(80);

	@Test
	void should_split_markdown_by_headings() {
		String markdown = """
				# 指标定义
				GMV 默认按订单明细汇总。

				## 取消订单
				取消订单不计入销售额。
				""";

		List<DocumentIndexBuilder.SourceDocument> chunks = chunker.chunk("metrics", Path.of("metrics.md"), "md", markdown);

		assertEquals(2, chunks.size());
		assertEquals("指标定义", chunks.get(0).sectionTitle());
		assertEquals("取消订单", chunks.get(1).sectionTitle());
	}

	@Test
	void should_split_long_section_by_length() {
		String text = "销售额口径：".repeat(30);

		List<DocumentIndexBuilder.SourceDocument> chunks = chunker.chunk("faq", Path.of("faq.txt"), "txt", text);

		assertTrue(chunks.size() >= 2);
		assertEquals(0, chunks.get(0).chunkIndex());
		assertEquals(1, chunks.get(1).chunkIndex());
	}

}
