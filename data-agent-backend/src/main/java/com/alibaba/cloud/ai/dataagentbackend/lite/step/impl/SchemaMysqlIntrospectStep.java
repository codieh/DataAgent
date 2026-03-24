package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaColumn;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaForeignKey;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * 数据库 schema 元数据抽取（MySQL）。
 *
 * <p>
 * 目标：
 * <ul>
 *   <li>不依赖人工描述，直接从 {@code information_schema} 抽取表/列/注释/主外键信息。</li>
 *   <li>生成一段适合喂给 LLM 的 {@code schemaText}，写入 {@link SearchLiteState}。</li>
 * </ul>
 * </p>
 *
 * <p>
 * 注意：JDBC 是阻塞调用，因此在 WebFlux 流水线中必须切换到 {@code boundedElastic} 执行。
 * </p>
 */
@Component
@Order(30)
@ConditionalOnProperty(name = "search.lite.schema.introspect.provider", havingValue = "mysql", matchIfMissing = true)
public class SchemaMysqlIntrospectStep implements SearchLiteStep {

	private static final Logger log = LoggerFactory.getLogger(SchemaMysqlIntrospectStep.class);

	private final JdbcTemplate jdbcTemplate;

	private final List<String> defaultTables;

	public SchemaMysqlIntrospectStep(JdbcTemplate jdbcTemplate,
			@Value("${search.lite.schema.tables:users,products,orders,order_items,categories,product_categories}") String tables) {
		this.jdbcTemplate = Objects.requireNonNull(jdbcTemplate, "jdbcTemplate");
		this.defaultTables = parseTables(tables);
	}

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.SCHEMA;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		Flux<SearchLiteMessage> start = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在加载数据库结构（schema）...", null))
			.delayElements(Duration.ofMillis(50));

		Mono<SchemaSnapshot> snapshotMono = Mono.fromCallable(() -> loadSchema(defaultTables))
			.subscribeOn(Schedulers.boundedElastic())
			.doOnSubscribe(s -> log.info("schema 抽取开始：threadId={}, tables={}", context.threadId(), defaultTables))
			.doOnSuccess(s -> log.info("schema 抽取完成：threadId={}, tables={}, tookTables={}", context.threadId(),
					defaultTables.size(), s == null ? 0 : s.tables.size()))
			.doOnError(e -> log.warn("schema 抽取失败：threadId={}, error={}", context.threadId(),
					e == null ? null : e.getMessage(), e))
			.cache();

		Flux<SearchLiteMessage> perTable = snapshotMono.flatMapMany(snapshot -> Flux.fromIterable(snapshot.tables)
			.concatMap(t -> Flux.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT,
					"表 " + t.name + "：共 " + t.columns.size() + " 列", null)).delayElements(Duration.ofMillis(30))));

	Mono<SearchLiteState> updated = snapshotMono.map(snapshot -> {
		state.setSchemaTables(snapshot.tables.stream().map(t -> t.name).toList());
		state.setSchemaText(snapshot.schemaText);
		state.setSchemaTableDetails(snapshot.tables.stream().map(TableInfo::toSchemaTable).toList());
		return state;
	});

		Flux<SearchLiteMessage> payload = snapshotMono.map(snapshot -> {
			Map<String, Object> data = new LinkedHashMap<>();
			data.put("tables", snapshot.tables.stream().map(TableInfo::toPayload).toList());
			data.put("schemaText", snapshot.schemaText);
			data.put("schemaTextLen", snapshot.schemaText == null ? 0 : snapshot.schemaText.length());
			return SearchLiteMessages.message(context, stage(), SearchLiteMessageType.JSON, null, data);
		}).flux();

		return new SearchLiteStepResult(start.concatWith(perTable).concatWith(payload), updated);
	}

	private SchemaSnapshot loadSchema(List<String> tables) {
		List<String> tableList = (tables == null || tables.isEmpty()) ? List.of() : tables;
		if (tableList.isEmpty()) {
			return new SchemaSnapshot(List.of(), "(schema tables not configured)");
		}

		Map<String, String> tableComments = loadTableComments(tableList);
		Map<String, List<ColumnInfo>> columnsByTable = loadColumns(tableList);
		Map<String, List<ForeignKeyInfo>> fksByTable = loadForeignKeys(tableList);

		List<TableInfo> infos = new ArrayList<>();
		for (String table : tableList) {
			List<ColumnInfo> cols = columnsByTable.getOrDefault(table, List.of());
			List<ForeignKeyInfo> fks = fksByTable.getOrDefault(table, List.of());
			String comment = tableComments.getOrDefault(table, "");
			infos.add(new TableInfo(table, comment, cols, fks));
		}

		String schemaText = formatForPrompt(infos);
		return new SchemaSnapshot(infos, schemaText);
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
		jdbcTemplate.query(sql, rs -> {
			map.put(rs.getString("table_name"), rs.getString("table_comment"));
		}, args);
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
			ColumnInfo col = new ColumnInfo(rs.getString("column_name"), rs.getString("data_type"),
					rs.getString("column_type"), rs.getString("is_nullable"), rs.getString("column_key"),
					rs.getString("column_comment"));
			map.computeIfAbsent(rs.getString("table_name"), k -> new ArrayList<>()).add(col);
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
			map.computeIfAbsent(rs.getString("table_name"), k -> new ArrayList<>()).add(fk);
		}, args);
		return map;
	}

	private static String formatForPrompt(List<TableInfo> tables) {
		if (tables == null || tables.isEmpty()) {
			return "(无 schema)";
		}
		StringBuilder sb = new StringBuilder();
		sb.append("数据库 Schema（节选）\n");
		for (TableInfo table : tables) {
			sb.append("\n");
			sb.append("TABLE ").append(table.name);
			if (table.comment != null && !table.comment.isBlank()) {
				sb.append(" -- ").append(table.comment.trim());
			}
			sb.append("\n");

			for (ColumnInfo col : table.columns) {
				sb.append("  - ").append(col.name).append(" ").append(safe(col.columnType, col.dataType));
				if ("PRI".equalsIgnoreCase(col.columnKey)) {
					sb.append(" PK");
				}
				if ("NO".equalsIgnoreCase(col.isNullable)) {
					sb.append(" NOT_NULL");
				}
				if (col.comment != null && !col.comment.isBlank()) {
					sb.append(" -- ").append(col.comment.trim());
				}
				sb.append("\n");
			}

			if (table.foreignKeys != null && !table.foreignKeys.isEmpty()) {
				sb.append("  FK:\n");
				for (ForeignKeyInfo fk : table.foreignKeys) {
					sb.append("    - ").append(fk.columnName).append(" -> ").append(fk.refTableName).append(".")
						.append(fk.refColumnName).append("\n");
				}
			}
		}
		return sb.toString().trim();
	}

	private static String safe(String... parts) {
		for (String p : parts) {
			if (p != null && !p.isBlank()) {
				return p.trim();
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

	private record SchemaSnapshot(List<TableInfo> tables, String schemaText) {
	}

	private record TableInfo(String name, String comment, List<ColumnInfo> columns, List<ForeignKeyInfo> foreignKeys) {
		Map<String, Object> toPayload() {
			Map<String, Object> m = new LinkedHashMap<>();
			m.put("name", name);
			m.put("comment", comment);
			m.put("columns", columns);
			m.put("foreignKeys", foreignKeys);
			return m;
		}

		SchemaTable toSchemaTable() {
			List<SchemaColumn> cols = columns == null ? List.of()
					: columns.stream().map(ColumnInfo::toSchemaColumn).toList();
			List<SchemaForeignKey> fks = foreignKeys == null ? List.of()
					: foreignKeys.stream().map(ForeignKeyInfo::toSchemaForeignKey).toList();
			return new SchemaTable(name, comment, cols, fks);
		}
	}

	private record ColumnInfo(String name, String dataType, String columnType, String isNullable, String columnKey,
			String comment) {
		SchemaColumn toSchemaColumn() {
			boolean notNull = "NO".equalsIgnoreCase(isNullable);
			boolean primaryKey = "PRI".equalsIgnoreCase(columnKey);
			return new SchemaColumn(name, dataType, columnType, notNull, primaryKey, comment);
		}
	}

	private record ForeignKeyInfo(String columnName, String refTableName, String refColumnName) {
		SchemaForeignKey toSchemaForeignKey() {
			return new SchemaForeignKey(columnName, refTableName, refColumnName);
		}
	}

}
