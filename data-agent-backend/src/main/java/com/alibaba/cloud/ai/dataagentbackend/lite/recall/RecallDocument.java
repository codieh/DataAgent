package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import java.util.Map;
import java.util.Objects;

/**
 * 检索基础设施中的统一文档模型。
 */
public record RecallDocument(String id, RecallDocumentType type, String title, String content,
		Map<String, Object> metadata) {

	public RecallDocument {
		id = Objects.requireNonNull(id, "id");
		type = Objects.requireNonNull(type, "type");
		title = title == null ? "" : title.trim();
		content = content == null ? "" : content.trim();
		metadata = metadata == null ? Map.of() : Map.copyOf(metadata);
	}

	public String searchableText() {
		if (title.isBlank()) {
			return content;
		}
		if (content.isBlank()) {
			return title;
		}
		return title + "\n" + content;
	}

}
