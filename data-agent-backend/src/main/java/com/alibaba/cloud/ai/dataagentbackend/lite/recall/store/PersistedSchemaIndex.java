package com.alibaba.cloud.ai.dataagentbackend.lite.recall.store;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocument;
import com.fasterxml.jackson.annotation.JsonIgnore;

import java.util.List;

/**
 * 持久化后的 schema 索引快照。
 */
public record PersistedSchemaIndex(List<SchemaTable> schemaTables, String schemaText, List<RecallDocument> tableDocuments,
		List<RecallDocument> columnDocuments) {

	public PersistedSchemaIndex {
		schemaTables = schemaTables == null ? List.of() : List.copyOf(schemaTables);
		schemaText = schemaText == null ? "" : schemaText;
		tableDocuments = tableDocuments == null ? List.of() : List.copyOf(tableDocuments);
		columnDocuments = columnDocuments == null ? List.of() : List.copyOf(columnDocuments);
	}

	@JsonIgnore
	public boolean isEmpty() {
		return schemaTables.isEmpty() && tableDocuments.isEmpty() && columnDocuments.isEmpty();
	}

}
