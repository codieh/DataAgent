package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaColumn;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaForeignKey;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.store.PersistedSchemaIndex;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.store.RecallDocumentStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 统一召回服务。
 *
 * <p>
 * 当前先统一 schema / evidence 的索引构建与关键词召回逻辑，
 * 后续再把底层替换为向量检索或混合检索。
 * </p>
 */
@Service
public class RecallService {

	private static final Logger log = LoggerFactory.getLogger(RecallService.class);

	private final RecallEngine recallEngine;

	private final EvidenceIndexBuilder evidenceIndexBuilder;

	private final SchemaIndexBuilder schemaIndexBuilder;

	private final RecallDocumentStore recallDocumentStore;

	private final RecallEmbeddingService recallEmbeddingService;

	private final EvidenceRecallMetadataResolver evidenceRecallMetadataResolver;

	public RecallService(RecallEngine recallEngine, EvidenceIndexBuilder evidenceIndexBuilder,
			SchemaIndexBuilder schemaIndexBuilder, RecallDocumentStore recallDocumentStore,
			RecallEmbeddingService recallEmbeddingService,
			EvidenceRecallMetadataResolver evidenceRecallMetadataResolver) {
		this.recallEngine = recallEngine;
		this.evidenceIndexBuilder = evidenceIndexBuilder;
		this.schemaIndexBuilder = schemaIndexBuilder;
		this.recallDocumentStore = recallDocumentStore;
		this.recallEmbeddingService = recallEmbeddingService;
		this.evidenceRecallMetadataResolver = evidenceRecallMetadataResolver;
	}

	public EvidenceRecallResult recallEvidence(String query, List<EvidenceItem> evidenceItems, int topK) {
		List<RecallDocument> documents = recallDocumentStore.loadEvidenceDocuments();
		boolean loadedFromStore = !documents.isEmpty();
		if (documents.isEmpty()) {
			documents = evidenceIndexBuilder.build(evidenceItems);
		}
		documents = persistEvidenceDocuments(documents);
		if (query == null || query.isBlank()) {
			return new EvidenceRecallResult(List.of(), formatEvidencePrompt(List.of()), List.of());
		}
		EvidenceRecallMetadataResolver.EvidenceRecallFilter filter = evidenceRecallMetadataResolver.resolve(query);
		List<RecallHit> hits = filter.isEmpty() ? List.of()
				: recallEngine.search(query, documents,
						new RecallOptions(topK, Set.of(RecallDocumentType.EVIDENCE), filter.toRequiredMetadata()));
		String filterMode = "none";
		if (!filter.isEmpty()) {
			filterMode = "metadata";
		}
		if (hits.isEmpty()) {
			hits = recallEngine.search(query, documents, new RecallOptions(topK, Set.of(RecallDocumentType.EVIDENCE), Map.of()));
			filterMode = filter.isEmpty() ? "none" : "fallback-all";
		}

		List<EvidenceItem> selected = hits.stream().map(this::toEvidenceItem).toList();
		logRecallHits("evidence", query,
				"%s,%s,%s".formatted(loadedFromStore ? "store" : "rebuild", filterMode, filter.summary()), hits);
		return new EvidenceRecallResult(selected, formatEvidencePrompt(selected), hits);
	}

	public SchemaRecallResult recallSchema(String query, String evidenceText, List<SchemaTable> schemaTables, int topK) {
		Optional<PersistedSchemaIndex> loaded = recallDocumentStore.loadSchemaIndex();
		PersistedSchemaIndex persisted = loaded
			.orElseGet(() -> persistSchemaIndex(schemaTables, formatSchemaPrompt(schemaTables)));
		SchemaIndex schemaIndex = new SchemaIndex(persisted.tableDocuments(), persisted.columnDocuments());
		List<SchemaTable> availableTables = persisted.schemaTables().isEmpty() ? schemaTables : persisted.schemaTables();
		String mergedQuery = safe(query) + "\n" + safe(evidenceText);

		List<RecallHit> tableHits = recallEngine.search(mergedQuery, schemaIndex.tableDocuments(),
				new RecallOptions(topK, Set.of(RecallDocumentType.SCHEMA_TABLE), Map.of()));

		List<String> tableNames = tableHits.stream()
			.map(hit -> (String) hit.document().metadata().get("tableName"))
			.filter(StringUtils::hasText)
			.distinct()
			.toList();

		List<SchemaTable> recalledTables = filterTables(availableTables, tableNames, topK);
		List<RecallHit> columnHits = tableNames.isEmpty() ? List.of()
				: recallEngine.search(mergedQuery, schemaIndex.columnDocuments(),
						new RecallOptions(Math.max(topK * 5, 10), Set.of(RecallDocumentType.SCHEMA_COLUMN), Map.of()));
		List<RecallHit> filteredColumnHits = filterColumnHitsByTables(columnHits, recalledTables);
		List<SchemaTable> focusedTables = focusTablesByColumnHits(recalledTables, filteredColumnHits);
		String promptText = formatSchemaPrompt(focusedTables);
		logRecallHits("schema-table", mergedQuery, loaded.isPresent() ? "store" : "rebuild", tableHits);
		logRecallHits("schema-column", mergedQuery, loaded.isPresent() ? "store" : "rebuild", filteredColumnHits);
		return new SchemaRecallResult(recalledTables, focusedTables, recalledTables.stream().map(SchemaTable::name).toList(),
				promptText, tableHits, filteredColumnHits);
	}

	public PersistedSchemaIndex persistSchemaIndex(List<SchemaTable> schemaTables, String schemaText) {
		SchemaIndex schemaIndex = schemaIndexBuilder.build(schemaTables);
		List<RecallDocument> tableDocuments = recallEmbeddingService.ensureEmbeddings(schemaIndex.tableDocuments());
		List<RecallDocument> columnDocuments = recallEmbeddingService.ensureEmbeddings(schemaIndex.columnDocuments());
		PersistedSchemaIndex persisted = new PersistedSchemaIndex(schemaTables, schemaText, tableDocuments, columnDocuments);
		recallDocumentStore.saveSchemaIndex(persisted);
		return persisted;
	}

	public List<RecallDocument> persistEvidenceDocuments(List<RecallDocument> documents) {
		List<RecallDocument> enriched = recallEmbeddingService.ensureEmbeddings(documents);
		recallDocumentStore.saveEvidenceDocuments(enriched);
		return enriched;
	}

	public Optional<PersistedSchemaIndex> loadPersistedSchemaIndex() {
		return recallDocumentStore.loadSchemaIndex();
	}

	public com.alibaba.cloud.ai.dataagentbackend.lite.recall.store.RecallIndexStatus indexStatus() {
		return recallDocumentStore.status();
	}

	private EvidenceItem toEvidenceItem(RecallHit hit) {
		RecallDocument doc = hit.document();
		Map<String, Object> metadata = new LinkedHashMap<>(doc.metadata());
		String source = metadata.get("source") == null ? "" : String.valueOf(metadata.get("source"));
		Double rawScore = metadata.get("rawScore") instanceof Number number ? number.doubleValue() : hit.score();
		String snippet = metadata.get("snippet") == null ? doc.content() : String.valueOf(metadata.get("snippet"));
		metadata = new LinkedHashMap<>(RecallEmbeddings.publicMetadata(metadata));
		metadata.remove("source");
		metadata.remove("rawScore");
		metadata.remove("snippet");
		return new EvidenceItem(doc.id(), doc.title(), snippet, source, rawScore, metadata);
	}

	private static List<SchemaTable> filterTables(List<SchemaTable> tables, List<String> tableNames, int topK) {
		if (tables == null || tables.isEmpty()) {
			return List.of();
		}
		if (tableNames == null || tableNames.isEmpty()) {
			return tables.stream().limit(topK).toList();
		}
		List<SchemaTable> filtered = tables.stream()
			.filter(table -> tableNames.contains(table.name()))
			.toList();
		return filtered.isEmpty() ? tables.stream().limit(topK).toList() : filtered;
	}

	private static List<RecallHit> filterColumnHitsByTables(List<RecallHit> hits, List<SchemaTable> tables) {
		if (hits == null || hits.isEmpty() || tables == null || tables.isEmpty()) {
			return List.of();
		}
		Set<String> tableNames = tables.stream().map(SchemaTable::name).collect(Collectors.toSet());
		return hits.stream().filter(hit -> {
			Object tableName = hit.document().metadata().get("tableName");
			return tableName != null && tableNames.contains(String.valueOf(tableName));
		}).toList();
	}

	private static List<SchemaTable> focusTablesByColumnHits(List<SchemaTable> recalledTables, List<RecallHit> columnHits) {
		if (recalledTables == null || recalledTables.isEmpty()) {
			return List.of();
		}
		Map<String, List<String>> matchedColumnsByTable = columnHits == null ? Map.of()
				: columnHits.stream()
					.collect(Collectors.groupingBy(hit -> String.valueOf(hit.document().metadata().get("tableName")),
							LinkedHashMap::new,
							Collectors.mapping(hit -> String.valueOf(hit.document().metadata().get("columnName")),
									Collectors.toList())));
		List<SchemaTable> focusedTables = new ArrayList<>();
		for (SchemaTable table : recalledTables) {
			if (table == null) {
				continue;
			}
			List<String> matchedColumns = matchedColumnsByTable.getOrDefault(table.name(), List.of());
			List<SchemaColumn> focusedColumns = focusColumns(table.columns(), matchedColumns);
			List<SchemaForeignKey> focusedForeignKeys = focusForeignKeys(table.foreignKeys(), focusedColumns);
			focusedTables.add(new SchemaTable(table.name(), table.comment(), focusedColumns, focusedForeignKeys));
		}
		return List.copyOf(focusedTables);
	}

	private static List<SchemaColumn> focusColumns(List<SchemaColumn> columns, List<String> matchedColumns) {
		if (columns == null || columns.isEmpty()) {
			return List.of();
		}
		if (matchedColumns == null || matchedColumns.isEmpty()) {
			return pickFallbackColumns(columns);
		}
		Set<String> selectedNames = new LinkedHashSet<>(matchedColumns);
		for (SchemaColumn column : columns) {
			if (column.primaryKey()) {
				selectedNames.add(column.name());
			}
		}
		List<SchemaColumn> focused = columns.stream().filter(column -> selectedNames.contains(column.name())).toList();
		return focused.isEmpty() ? pickFallbackColumns(columns) : focused;
	}

	private static List<SchemaColumn> pickFallbackColumns(List<SchemaColumn> columns) {
		List<SchemaColumn> primaryKeys = columns.stream().filter(SchemaColumn::primaryKey).toList();
		LinkedHashSet<SchemaColumn> selected = new LinkedHashSet<>(primaryKeys);
		columns.stream().limit(4).forEach(selected::add);
		return List.copyOf(selected);
	}

	private static List<SchemaForeignKey> focusForeignKeys(List<SchemaForeignKey> foreignKeys, List<SchemaColumn> focusedColumns) {
		if (foreignKeys == null || foreignKeys.isEmpty() || focusedColumns == null || focusedColumns.isEmpty()) {
			return List.of();
		}
		Set<String> columnNames = focusedColumns.stream().map(SchemaColumn::name).collect(Collectors.toSet());
		return foreignKeys.stream().filter(fk -> columnNames.contains(fk.columnName())).toList();
	}

	private static String formatEvidencePrompt(List<EvidenceItem> items) {
		if (items == null || items.isEmpty()) {
			return "(无证据)";
		}
		StringBuilder sb = new StringBuilder();
		for (int i = 0; i < items.size(); i++) {
			EvidenceItem item = items.get(i);
			sb.append("[证据").append(i + 1).append("] ")
				.append(safe(item.title()))
				.append(": ")
				.append(safe(item.snippet()))
				.append("\n");
		}
		return sb.toString().trim();
	}

	private static String formatSchemaPrompt(List<SchemaTable> tables) {
		if (tables == null || tables.isEmpty()) {
			return "(无 schema)";
		}
		StringBuilder sb = new StringBuilder();
		sb.append("数据库 Schema（本次相关表）\n");
		for (SchemaTable table : tables) {
			sb.append("\nTABLE ").append(safe(table.name()));
			if (StringUtils.hasText(table.comment())) {
				sb.append(" -- ").append(table.comment().trim());
			}
			sb.append("\n");

			if (table.columns() != null) {
				for (SchemaColumn column : table.columns()) {
					sb.append("  - ").append(safe(column.name())).append(" ").append(safe(column.columnType(), column.dataType()));
					if (column.primaryKey()) {
						sb.append(" PK");
					}
					if (column.notNull()) {
						sb.append(" NOT_NULL");
					}
					if (StringUtils.hasText(column.comment())) {
						sb.append(" -- ").append(column.comment().trim());
					}
					sb.append("\n");
				}
			}

			if (table.foreignKeys() != null && !table.foreignKeys().isEmpty()) {
				sb.append("  FK:\n");
				for (SchemaForeignKey fk : table.foreignKeys()) {
					sb.append("    - ").append(safe(fk.columnName())).append(" -> ").append(safe(fk.refTableName()))
						.append(".").append(safe(fk.refColumnName())).append("\n");
				}
			}
		}
		return sb.toString().trim();
	}

	private static String safe(String... texts) {
		for (String text : texts) {
			if (StringUtils.hasText(text)) {
				return text.trim();
			}
		}
		return "";
	}

	private void logRecallHits(String channel, String query, String source, List<RecallHit> hits) {
		if (!log.isInfoEnabled()) {
			return;
		}
		String summary = hits == null || hits.isEmpty() ? "(empty)"
				: hits.stream()
					.limit(5)
					.map(hit -> "%s(score=%.2f, terms=%s)".formatted(hit.document().id(), hit.score(), hit.matchedTerms()))
					.collect(Collectors.joining("; "));
		log.info("recall 命中：channel={}, source={}, queryLen={}, hits={}", channel, source,
				query == null ? 0 : query.length(), summary);
	}

}
