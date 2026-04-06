package com.alibaba.cloud.ai.dataagentbackend.lite.knowledge;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocument;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocumentType;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertTrue;

class KnowledgeContextFormatterTest {

	private final KnowledgeContextFormatter formatter = new KnowledgeContextFormatter();

	@Test
	void should_format_evidence_as_rule_section() {
		String text = formatter.formatEvidenceContext(List.of(
				new EvidenceItem("e1", "核心用户定义", "近30天支付且退款率低于5%", "mock://kb/users/core", 0.9,
						Map.of("topic", "user"))));

		assertTrue(text.contains("业务规则与FAQ提示"));
		assertTrue(text.contains("[核心用户定义]"));
		assertTrue(text.contains("来源: mock://kb/users/core"));
	}

	@Test
	void should_format_documents_as_definition_section() {
		RecallDocument document = new RecallDocument("doc-1", RecallDocumentType.DOCUMENT, "user-segments",
				"高消费用户：按 total_amount 排名靠前的用户", Map.of("sectionTitle", "用户分层定义"));

		String text = formatter.formatDocumentContext(List.of(document));

		assertTrue(text.contains("定义与背景文档"));
		assertTrue(text.contains("[user-segments / 用户分层定义]"));
		assertTrue(text.contains("高消费用户"));
	}
}
