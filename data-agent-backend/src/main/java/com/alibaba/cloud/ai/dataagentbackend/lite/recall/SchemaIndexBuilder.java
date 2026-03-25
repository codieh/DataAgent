package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaColumn;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaForeignKey;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 将当前请求中的 schema 元信息转换为统一的可检索文档。
 *
 * <p>
 * 当前 builder 仅负责“结构化转文档”，不负责存储与召回。
 * 后续可继续演进为：
 * </p>
 * <ul>
 *     <li>启动时构建并缓存 schema index</li>
 *     <li>接入向量存储或混合检索</li>
 * </ul>
 */
@Component
public class SchemaIndexBuilder {

	public SchemaIndex build(List<SchemaTable> schemaTables) {
		if (schemaTables == null || schemaTables.isEmpty()) {
			return new SchemaIndex(List.of(), List.of());
		}

		List<RecallDocument> tableDocuments = new ArrayList<>();
		List<RecallDocument> columnDocuments = new ArrayList<>();

		for (SchemaTable table : schemaTables) {
			if (table == null || isBlank(table.name())) {
				continue;
			}
			tableDocuments.add(toTableDocument(table));

			if (table.columns() == null || table.columns().isEmpty()) {
				continue;
			}
			for (SchemaColumn column : table.columns()) {
				if (column == null || isBlank(column.name())) {
					continue;
				}
				columnDocuments.add(toColumnDocument(table, column));
			}
		}

		return new SchemaIndex(tableDocuments, columnDocuments);
	}

	private RecallDocument toTableDocument(SchemaTable table) {
		Map<String, Object> metadata = new LinkedHashMap<>();
		metadata.put("tableName", table.name());
		metadata.put("comment", safe(table.comment()));
		metadata.put("columnCount", table.columns() == null ? 0 : table.columns().size());
		metadata.put("foreignKeyCount", table.foreignKeys() == null ? 0 : table.foreignKeys().size());

		StringBuilder content = new StringBuilder();
		content.append("表名: ").append(table.name());
		if (!isBlank(table.comment())) {
			content.append("，说明: ").append(table.comment().trim());
		}
		if (table.columns() != null && !table.columns().isEmpty()) {
			content.append("，字段: ");
			for (int i = 0; i < table.columns().size(); i++) {
				SchemaColumn column = table.columns().get(i);
				content.append(column.name());
				if (!isBlank(column.comment())) {
					content.append("(").append(column.comment().trim()).append(")");
				}
				if (i < table.columns().size() - 1) {
					content.append("、");
				}
			}
		}
		if (table.foreignKeys() != null && !table.foreignKeys().isEmpty()) {
			content.append("，外键关系: ");
			for (int i = 0; i < table.foreignKeys().size(); i++) {
				SchemaForeignKey fk = table.foreignKeys().get(i);
				content.append(fk.columnName()).append("->").append(fk.refTableName()).append(".")
					.append(fk.refColumnName());
				if (i < table.foreignKeys().size() - 1) {
					content.append("；");
				}
			}
		}

		return new RecallDocument("schema-table:" + table.name(), RecallDocumentType.SCHEMA_TABLE, table.name(),
				content.toString(), metadata);
	}

	private RecallDocument toColumnDocument(SchemaTable table, SchemaColumn column) {
		Map<String, Object> metadata = new LinkedHashMap<>();
		metadata.put("tableName", table.name());
		metadata.put("columnName", column.name());
		metadata.put("dataType", safe(column.dataType()));
		metadata.put("columnType", safe(column.columnType()));
		metadata.put("primaryKey", column.primaryKey());
		metadata.put("notNull", column.notNull());

		StringBuilder content = new StringBuilder();
		content.append("字段: ").append(table.name()).append(".").append(column.name());
		if (!isBlank(column.comment())) {
			content.append("，说明: ").append(column.comment().trim());
		}
		if (!isBlank(column.dataType())) {
			content.append("，数据类型: ").append(column.dataType().trim());
		}
		if (column.primaryKey()) {
			content.append("，主键");
		}
		if (column.notNull()) {
			content.append("，非空");
		}

		String title = table.name() + "." + column.name();
		return new RecallDocument("schema-column:" + title, RecallDocumentType.SCHEMA_COLUMN, title, content.toString(),
				metadata);
	}

	private static boolean isBlank(String text) {
		return text == null || text.isBlank();
	}

	private static String safe(String text) {
		return text == null ? "" : text;
	}

}
