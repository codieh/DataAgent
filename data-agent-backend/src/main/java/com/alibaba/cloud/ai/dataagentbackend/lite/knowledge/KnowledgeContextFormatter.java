package com.alibaba.cloud.ai.dataagentbackend.lite.knowledge;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocument;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
public class KnowledgeContextFormatter {

	public String formatEvidenceContext(List<EvidenceItem> evidences) {
		if (evidences == null || evidences.isEmpty()) {
			return "(无业务规则提示)";
		}
		StringBuilder builder = new StringBuilder("业务规则与FAQ提示：\n");
		int index = 1;
		for (EvidenceItem item : evidences) {
			builder.append(index++)
				.append(". [")
				.append(safe(item.title()))
				.append("] ")
				.append(safe(item.snippet()));
			if (!safe(item.source()).isBlank()) {
				builder.append(" (来源: ").append(safe(item.source())).append(")");
			}
			builder.append('\n');
		}
		return builder.toString().trim();
	}

	public String formatDocumentContext(List<RecallDocument> documents) {
		if (documents == null || documents.isEmpty()) {
			return "(无文档定义补充)";
		}
		StringBuilder builder = new StringBuilder("定义与背景文档：\n");
		int index = 1;
		for (RecallDocument document : documents) {
			String sectionTitle = String.valueOf(document.metadata().getOrDefault("sectionTitle", ""));
			builder.append(index++)
				.append(". [")
				.append(safe(document.title()));
			if (!safe(sectionTitle).isBlank()) {
				builder.append(" / ").append(safe(sectionTitle));
			}
			builder.append("] ")
				.append(safe(document.content()))
				.append('\n');
		}
		return builder.toString().trim();
	}

	private static String safe(String value) {
		return value == null ? "" : value.trim();
	}

}
