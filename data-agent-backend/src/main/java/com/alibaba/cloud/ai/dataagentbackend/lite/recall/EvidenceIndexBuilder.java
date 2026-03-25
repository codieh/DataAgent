package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 将 evidence 数据统一转换为可检索文档。
 */
@Component
public class EvidenceIndexBuilder {

	public List<RecallDocument> build(List<EvidenceItem> evidenceItems) {
		if (evidenceItems == null || evidenceItems.isEmpty()) {
			return List.of();
		}

		List<RecallDocument> documents = new ArrayList<>();
		for (EvidenceItem item : evidenceItems) {
			if (item == null || isBlank(item.id())) {
				continue;
			}
			documents.add(toDocument(item));
		}
		return List.copyOf(documents);
	}

	private RecallDocument toDocument(EvidenceItem item) {
		Map<String, Object> metadata = new LinkedHashMap<>();
		metadata.put("source", safe(item.source()));
		metadata.put("rawScore", item.score());
		metadata.put("snippet", safe(item.snippet()));
		if (item.metadata() != null && !item.metadata().isEmpty()) {
			metadata.putAll(item.metadata());
		}

		StringBuilder content = new StringBuilder();
		content.append("标题: ").append(safe(item.title()));
		if (!isBlank(item.snippet())) {
			content.append("，内容: ").append(item.snippet().trim());
		}
		if (!isBlank(item.source())) {
			content.append("，来源: ").append(item.source().trim());
		}

		return new RecallDocument(item.id(), RecallDocumentType.EVIDENCE, safe(item.title()), content.toString(),
				metadata);
	}

	private static boolean isBlank(String text) {
		return text == null || text.isBlank();
	}

	private static String safe(String text) {
		return text == null ? "" : text;
	}

}
