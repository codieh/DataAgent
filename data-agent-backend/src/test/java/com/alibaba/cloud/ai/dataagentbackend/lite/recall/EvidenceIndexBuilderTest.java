package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EvidenceIndexBuilderTest {

	private final EvidenceIndexBuilder builder = new EvidenceIndexBuilder();

	@Test
	void should_convert_evidence_items_to_recall_documents() {
		List<EvidenceItem> items = List.of(
				new EvidenceItem("metric-gmv-1", "GMV 指标口径", "GMV 默认按支付金额合计统计", "mock://gmv", 0.9,
						Map.of("type", "DOC", "tags", List.of("metric", "gmv"))));

		List<RecallDocument> documents = builder.build(items);

		assertEquals(1, documents.size());
		assertEquals(RecallDocumentType.EVIDENCE, documents.get(0).type());
		assertEquals("GMV 指标口径", documents.get(0).title());
		assertTrue(documents.get(0).content().contains("支付金额"));
		assertEquals("DOC", documents.get(0).metadata().get("type"));
		assertEquals("sales", documents.get(0).metadata().get("topic"));
		assertEquals(List.of("metric", "gmv", "sales"), documents.get(0).metadata().get("tags"));
	}

}
