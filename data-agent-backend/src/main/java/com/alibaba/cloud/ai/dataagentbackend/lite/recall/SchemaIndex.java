package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import java.util.List;

/**
 * Schema 索引结果，分别保存表文档与列文档。
 */
public record SchemaIndex(List<RecallDocument> tableDocuments, List<RecallDocument> columnDocuments) {

	public SchemaIndex {
		tableDocuments = tableDocuments == null ? List.of() : List.copyOf(tableDocuments);
		columnDocuments = columnDocuments == null ? List.of() : List.copyOf(columnDocuments);
	}

	public List<RecallDocument> allDocuments() {
		if (tableDocuments.isEmpty()) {
			return columnDocuments;
		}
		if (columnDocuments.isEmpty()) {
			return tableDocuments;
		}
		List<RecallDocument> merged = new java.util.ArrayList<>(tableDocuments.size() + columnDocuments.size());
		merged.addAll(tableDocuments);
		merged.addAll(columnDocuments);
		return List.copyOf(merged);
	}

}
