package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;

import java.util.List;

/**
 * Schema 召回结果。
 */
public record SchemaRecallResult(List<SchemaTable> tables, List<String> tableNames, String promptText, List<RecallHit> tableHits,
		List<RecallHit> columnHits) {

	public SchemaRecallResult {
		tables = tables == null ? List.of() : List.copyOf(tables);
		tableNames = tableNames == null ? List.of() : List.copyOf(tableNames);
		promptText = promptText == null ? "" : promptText;
		tableHits = tableHits == null ? List.of() : List.copyOf(tableHits);
		columnHits = columnHits == null ? List.of() : List.copyOf(columnHits);
	}

}
