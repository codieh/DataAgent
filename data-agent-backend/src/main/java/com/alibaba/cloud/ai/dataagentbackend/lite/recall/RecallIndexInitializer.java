package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaColumn;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaForeignKey;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import com.alibaba.cloud.ai.dataagentbackend.lite.evidence.EvidenceRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * 显式索引初始化服务。
 *
 * <p>
 * 负责将 evidence/schema 主动重建为本地持久化索引，而不是等请求时被动触发。
 * </p>
 */
@Service
public class RecallIndexInitializer {

	private static final Logger log = LoggerFactory.getLogger(RecallIndexInitializer.class);

	private final EvidenceRepository evidenceRepository;

	private final RecallService recallService;

	private final EvidenceIndexBuilder evidenceIndexBuilder;

	private final JdbcTemplate jdbcTemplate;

	private final List<String> defaultTables;

	public RecallIndexInitializer(EvidenceRepository evidenceRepository, RecallService recallService,
			EvidenceIndexBuilder evidenceIndexBuilder,
			JdbcTemplate jdbcTemplate,
			@Value("${search.lite.schema.tables:users,products,orders,order_items,categories,product_categories}") String tables) {
		this.evidenceRepository = Objects.requireNonNull(evidenceRepository, "evidenceRepository");
		this.recallService = Objects.requireNonNull(recallService, "recallService");
		this.evidenceIndexBuilder = Objects.requireNonNull(evidenceIndexBuilder, "evidenceIndexBuilder");
		this.jdbcTemplate = Objects.requireNonNull(jdbcTemplate, "jdbcTemplate");
		this.defaultTables = parseTables(tables);
	}

	public Map<String, Object> rebuildEvidenceIndex() {
		long start = System.currentTimeMillis();
		List<EvidenceItem> evidences = evidenceRepository.listAll();
		int count = recallService.persistEvidenceDocuments(evidenceIndexBuilder.build(evidences)).size();
		log.info("索引重建完成：type=evidence, source=repository, count={}, tookMs={}", count,
				System.currentTimeMillis() - start);
		return Map.of("count", count, "ok", true);
	}

	public Map<String, Object> rebuildSchemaIndex() {
		long start = System.currentTimeMillis();
		List<SchemaTable> schemaTables = loadSchemaTables(defaultTables);
		String schemaText = formatSchemaPrompt(schemaTables);
		recallService.persistSchemaIndex(schemaTables, schemaText);
		log.info("索引重建完成：type=schema, tables={}, tookMs={}",
				schemaTables.stream().map(SchemaTable::name).toList(), System.currentTimeMillis() - start);
		return Map.of("count", schemaTables.size(), "tables", schemaTables.stream().map(SchemaTable::name).toList(),
				"ok", true);
	}

	public Map<String, Object> rebuildAll() {
		Map<String, Object> evidence = rebuildEvidenceIndex();
		Map<String, Object> schema = rebuildSchemaIndex();
		return Map.of("evidence", evidence, "schema", schema, "ok", true);
	}

	private List<SchemaTable> loadSchemaTables(List<String> tables) {
		if (tables == null || tables.isEmpty()) {
			return List.of();
		}

		Map<String, String> tableComments = loadTableComments(tables);
		Map<String, List<ColumnInfo>> columnsByTable = loadColumns(tables);
		Map<String, List<ForeignKeyInfo>> fksByTable = loadForeignKeys(tables);

		List<SchemaTable> schemaTables = new ArrayList<>();
		for (String table : tables) {
			List<SchemaColumn> columns = columnsByTable.getOrDefault(table, List.of()).stream().map(ColumnInfo::toSchemaColumn)
				.toList();
			List<SchemaForeignKey> foreignKeys = fksByTable.getOrDefault(table, List.of()).stream()
				.map(ForeignKeyInfo::toSchemaForeignKey)
				.toList();
			schemaTables.add(new SchemaTable(table, tableComments.getOrDefault(table, ""), columns, foreignKeys));
		}
		return schemaTables;
	}

	private Map<String, String> loadTableComments(List<String> tables) {
		String in = tables.stream().map(t -> "?").collect(Collectors.joining(","));
		String sql = """
				SELECT table_name, table_comment
				FROM information_schema.tables
				WHERE table_schema = DATABASE()
				  AND table_name IN (%s)
				""".formatted(in);
		Object[] args = tables.toArray();
		Map<String, String> map = new HashMap<>();
		jdbcTemplate.query(sql, (org.springframework.jdbc.core.RowCallbackHandler) rs -> map.put(rs.getString("table_name"),
				rs.getString("table_comment")), args);
		return map;
	}

	private Map<String, List<ColumnInfo>> loadColumns(List<String> tables) {
		String in = tables.stream().map(t -> "?").collect(Collectors.joining(","));
		String sql = """
				SELECT table_name, column_name, data_type, column_type, is_nullable, column_key, column_comment, ordinal_position
				FROM information_schema.columns
				WHERE table_schema = DATABASE()
				  AND table_name IN (%s)
				ORDER BY table_name, ordinal_position
				""".formatted(in);
		Object[] args = tables.toArray();
		Map<String, List<ColumnInfo>> map = new HashMap<>();
		jdbcTemplate.query(sql, rs -> {
			ColumnInfo column = new ColumnInfo(rs.getString("column_name"), rs.getString("data_type"),
					rs.getString("column_type"), rs.getString("is_nullable"), rs.getString("column_key"),
					rs.getString("column_comment"));
			map.computeIfAbsent(rs.getString("table_name"), key -> new ArrayList<>()).add(column);
		}, args);
		return map;
	}

	private Map<String, List<ForeignKeyInfo>> loadForeignKeys(List<String> tables) {
		String in = tables.stream().map(t -> "?").collect(Collectors.joining(","));
		String sql = """
				SELECT table_name, column_name, referenced_table_name, referenced_column_name
				FROM information_schema.key_column_usage
				WHERE table_schema = DATABASE()
				  AND referenced_table_name IS NOT NULL
				  AND table_name IN (%s)
				""".formatted(in);
		Object[] args = tables.toArray();
		Map<String, List<ForeignKeyInfo>> map = new HashMap<>();
		jdbcTemplate.query(sql, rs -> {
			ForeignKeyInfo fk = new ForeignKeyInfo(rs.getString("column_name"), rs.getString("referenced_table_name"),
					rs.getString("referenced_column_name"));
			map.computeIfAbsent(rs.getString("table_name"), key -> new ArrayList<>()).add(fk);
		}, args);
		return map;
	}

	private static String formatSchemaPrompt(List<SchemaTable> tables) {
		if (tables == null || tables.isEmpty()) {
			return "(无 schema)";
		}
		StringBuilder sb = new StringBuilder();
		sb.append("数据库 Schema（节选）\n");
		for (SchemaTable table : tables) {
			sb.append("\nTABLE ").append(table.name());
			if (table.comment() != null && !table.comment().isBlank()) {
				sb.append(" -- ").append(table.comment().trim());
			}
			sb.append("\n");
			if (table.columns() != null) {
				for (SchemaColumn column : table.columns()) {
					sb.append("  - ").append(column.name()).append(" ")
						.append(firstNonBlank(column.columnType(), column.dataType()));
					if (column.primaryKey()) {
						sb.append(" PK");
					}
					if (column.notNull()) {
						sb.append(" NOT_NULL");
					}
					if (column.comment() != null && !column.comment().isBlank()) {
						sb.append(" -- ").append(column.comment().trim());
					}
					sb.append("\n");
				}
			}
		}
		return sb.toString().trim();
	}

	private static String firstNonBlank(String... texts) {
		for (String text : texts) {
			if (text != null && !text.isBlank()) {
				return text.trim();
			}
		}
		return "";
	}

	private static List<String> parseTables(String tables) {
		if (tables == null || tables.isBlank()) {
			return List.of();
		}
		return List.of(tables.split(",")).stream().map(String::trim).filter(s -> !s.isBlank()).toList();
	}

	private record ColumnInfo(String name, String dataType, String columnType, String isNullable, String columnKey,
			String comment) {
		SchemaColumn toSchemaColumn() {
			return new SchemaColumn(name, dataType, columnType, "NO".equalsIgnoreCase(isNullable),
					"PRI".equalsIgnoreCase(columnKey), comment);
		}
	}

	private record ForeignKeyInfo(String columnName, String refTableName, String refColumnName) {
		SchemaForeignKey toSchemaForeignKey() {
			return new SchemaForeignKey(columnName, refTableName, refColumnName);
		}
	}

}
