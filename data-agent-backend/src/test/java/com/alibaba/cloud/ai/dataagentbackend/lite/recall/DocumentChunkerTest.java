package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.DocumentIndexBuilder.SourceDocument;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentChunkerTest {

	private final DocumentChunker chunker = new DocumentChunker(100, 20);

	@Test
	void should_split_markdown_by_headings() {
		String markdown = """
				# 指标定义
				GMV 默认按订单明细汇总。

				## 取消订单
				取消订单不计入销售额。
				""";

		List<SourceDocument> chunks = chunker.chunk("metrics", Path.of("metrics.md"), "md", markdown);

		assertEquals(2, chunks.size());
		assertEquals("指标定义", chunks.get(0).sectionTitle());
		assertEquals("取消订单", chunks.get(1).sectionTitle());
	}

	@Test
	void should_split_long_section_by_length() {
		String text = "销售额口径：".repeat(30);

		List<SourceDocument> chunks = chunker.chunk("faq", Path.of("faq.txt"), "txt", text);

		assertTrue(chunks.size() >= 2);
		assertEquals(0, chunks.get(0).chunkIndex());
		assertEquals(1, chunks.get(1).chunkIndex());
	}

	@Test
	void should_split_long_section_by_sentence_with_overlap() {
		String text = """
				第一句用于定义销售额口径并解释基础范围。
				第二句补充有效订单和取消订单的区别。
				第三句说明近7天统计窗口和按下单时间计算。
				第四句说明退款订单需要单独排除。
				第五句继续补充同一段里的限制条件。
				""";

		List<SourceDocument> chunks = chunker.chunk("faq", Path.of("faq.txt"), "txt", text);

		assertTrue(chunks.size() >= 2);
		assertTrue(chunks.get(0).content().contains("第一句用于定义销售额口径并解释基础范围。"));
		assertTrue(chunks.get(0).content().contains("第二句补充有效订单和取消订单的区别。"));
		assertTrue(chunks.get(1).content().contains("第二句补充有效订单和取消订单的区别。")
				|| chunks.get(1).content().contains("第三句说明近7天统计窗口和按下单时间计算。"));
	}

}
