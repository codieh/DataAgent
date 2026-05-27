package com.alibaba.cloud.ai.dataagentbackend.lite.recall.pgvector;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocument;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocumentType;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallEmbeddings;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallHit;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallMetadataMatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallOptions;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding.EmbeddingClient;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

@Component
public class PgVectorSearchService {

	private static final Logger log = LoggerFactory.getLogger(PgVectorSearchService.class);

	private static final TypeReference<LinkedHashMap<String, Object>> METADATA_TYPE = new TypeReference<>() {
	};

	private final PgVectorProperties properties;

	private final EmbeddingClient embeddingClient;

	private final ObjectMapper objectMapper;

	private final JdbcTemplate jdbcTemplate;

	private volatile boolean schemaReady;

	public PgVectorSearchService(PgVectorProperties properties, EmbeddingClient embeddingClient, ObjectMapper objectMapper,
			@Qualifier("pgVectorJdbcTemplate") JdbcTemplate jdbcTemplate) {
		this.properties = Objects.requireNonNull(properties, "properties");
		this.embeddingClient = Objects.requireNonNull(embeddingClient, "embeddingClient");
		this.objectMapper = Objects.requireNonNull(objectMapper, "objectMapper");
		this.jdbcTemplate = Objects.requireNonNull(jdbcTemplate, "jdbcTemplate");
		log.info("pgvector jdbc initialized: enabled={}, url={}, username={}, tableName={}, dimensions={}, syncOnSearch={}",
				properties.enabled(), properties.url(), properties.username(), properties.tableName(),
				properties.dimensions(), properties.syncOnSearch());
	}

	public boolean isEnabled() {
		return properties.enabled();
	}

	public List<RecallHit> search(String query, List<RecallDocument> documents, RecallOptions options) {
		if (!isEnabled()) {
			log.info("pgvector search skipped: enabled=false");
			return List.of();
		}
		RecallOptions effectiveOptions = options == null ? RecallOptions.defaults() : options;
		List<Double> queryEmbedding = embeddingClient.embed(query);
		if (queryEmbedding.isEmpty()) {
			log.warn("pgvector: embedding returned empty vector, skip search");
			return List.of();
		}
		ensureSchema();
		boolean synced = false;
		if (properties.syncOnSearch()) {
			syncDocuments(documents);
			synced = true;
		}
		int requestedTopK = Math.max(1, effectiveOptions.topK());
		int candidateLimit = Math.max(requestedTopK * 5, requestedTopK + 10);
		String vectorLiteral = toVectorLiteral(queryEmbedding);
		String sql = """
				SELECT id, recall_type, title, content, metadata::text AS metadata_json,
				       1 - (embedding <=> CAST(? AS vector)) AS score
				FROM %s
				ORDER BY embedding <=> CAST(? AS vector)
				LIMIT ?
				""".formatted(properties.tableName());
		List<Map<String, Object>> rows = jdbcTemplate.queryForList(sql, vectorLiteral, vectorLiteral, candidateLimit);
		List<RecallHit> hits = new ArrayList<>();
		int typeMismatch = 0;
		int metadataMismatch = 0;
		int nonPositiveScore = 0;
		List<String> candidatePreview = log.isDebugEnabled() ? new ArrayList<>() : List.of();
		for (Map<String, Object> row : rows) {
			String id = stringValue(row.get("id"));
			double score = numberValue(row.get("score"));
			if (log.isDebugEnabled() && candidatePreview.size() < 5) {
				candidatePreview.add(formatCandidatePreview(id, row.get("recall_type"), score));
			}
			Map<String, Object> metadata = parseMetadata(row.get("metadata_json"));
			RecallDocument document = rebuildDocument(id, row.get("content"), row.get("title"), row.get("recall_type"),
					metadata);
			if (!matchesType(document, effectiveOptions.types())) {
				typeMismatch++;
				continue;
			}
			if (!RecallMetadataMatcher.matches(document, effectiveOptions.requiredMetadata())) {
				metadataMismatch++;
				continue;
			}
			if (score > 0) {
				hits.add(new RecallHit(document, score, List.of("pgvector")));
			}
			else {
				nonPositiveScore++;
			}
		}
		List<RecallHit> result = hits.stream()
			.sorted(Comparator.comparingDouble(RecallHit::score).reversed())
			.limit(requestedTopK)
			.toList();
		log.info(
				"pgvector search: queryLen={}, synced={}, syncDocCount={}, dbRows={}, filteredHits={}, typeMismatch={}, metadataMismatch={}, nonPositiveScore={}, topK={}, returned={}",
				query == null ? 0 : query.length(), synced, documents == null ? 0 : documents.size(), rows.size(),
				hits.size(), typeMismatch, metadataMismatch, nonPositiveScore, requestedTopK, result.size());
		if (log.isDebugEnabled() && !candidatePreview.isEmpty()) {
			log.debug("pgvector candidates: {}", candidatePreview);
		}
		return result;
	}

	private void syncDocuments(List<RecallDocument> documents) {
		if (documents == null || documents.isEmpty()) {
			return;
		}
		List<RecallDocument> withEmbeddings = documents.stream().filter(RecallEmbeddings::hasEmbedding).toList();
		if (withEmbeddings.isEmpty()) {
			return;
		}
		String sql = """
				INSERT INTO %s (id, recall_type, title, content, metadata, embedding, updated_at)
				VALUES (?, ?, ?, ?, CAST(? AS jsonb), CAST(? AS vector), CURRENT_TIMESTAMP)
				ON CONFLICT (id) DO UPDATE
				SET recall_type = EXCLUDED.recall_type,
				    title = EXCLUDED.title,
				    content = EXCLUDED.content,
				    metadata = EXCLUDED.metadata,
				    embedding = EXCLUDED.embedding,
				    updated_at = CURRENT_TIMESTAMP
				""".formatted(properties.tableName());
		jdbcTemplate.batchUpdate(sql, new BatchPreparedStatementSetter() {
			@Override
			public void setValues(PreparedStatement ps, int i) throws SQLException {
				RecallDocument document = withEmbeddings.get(i);
				ps.setString(1, document.id());
				ps.setString(2, document.type().name());
				ps.setString(3, document.title());
				ps.setString(4, document.content());
				ps.setString(5, toMetadataJson(document));
				ps.setString(6, toVectorLiteral(RecallEmbeddings.embedding(document)));
			}

			@Override
			public int getBatchSize() {
				return withEmbeddings.size();
			}
		});
	}

	private void ensureSchema() {
		if (schemaReady) {
			return;
		}
		synchronized (this) {
			if (schemaReady) {
				return;
			}
			jdbcTemplate.execute("CREATE EXTENSION IF NOT EXISTS vector");
			jdbcTemplate.execute("""
					CREATE TABLE IF NOT EXISTS %s (
					    id TEXT PRIMARY KEY,
					    recall_type TEXT NOT NULL,
					    title TEXT NOT NULL,
					    content TEXT NOT NULL,
					    metadata JSONB NOT NULL,
					    embedding vector(%d) NOT NULL,
					    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
					)
					""".formatted(properties.tableName(), properties.dimensions()));
			try {
				jdbcTemplate.execute("""
						CREATE INDEX IF NOT EXISTS %s_embedding_ivfflat
						ON %s USING ivfflat (embedding vector_cosine_ops)
						WITH (lists = 100)
						""".formatted(properties.tableName(), properties.tableName()));
			}
			catch (Exception ex) {
				log.warn("pgvector index create skipped: {}", ex.getMessage());
			}
			schemaReady = true;
		}
	}

	private String toMetadataJson(RecallDocument document) {
		Map<String, Object> metadata = new LinkedHashMap<>();
		metadata.put("recallType", document.type().name());
		metadata.put("title", document.title());
		metadata.putAll(RecallEmbeddings.publicMetadata(document.metadata()));
		try {
			return objectMapper.writeValueAsString(metadata);
		}
		catch (Exception ex) {
			throw new IllegalStateException("Failed to serialize pgvector recall metadata", ex);
		}
	}

	private Map<String, Object> parseMetadata(Object raw) {
		if (raw == null) {
			return Map.of();
		}
		try {
			String json = String.valueOf(raw);
			if (json.isBlank()) {
				return Map.of();
			}
			Map<String, Object> metadata = objectMapper.readValue(json, METADATA_TYPE);
			metadata.remove("title");
			metadata.remove("recallType");
			return metadata;
		}
		catch (Exception ex) {
			log.warn("pgvector metadata parse failed: {}", ex.getMessage());
			return Map.of();
		}
	}

	private RecallDocument rebuildDocument(String id, Object content, Object title, Object type, Map<String, Object> metadata) {
		String restoredTitle = title == null ? id : String.valueOf(title);
		RecallDocumentType restoredType = parseType(type);
		return new RecallDocument(id, restoredType, restoredTitle, content == null ? "" : String.valueOf(content), metadata);
	}

	private static boolean matchesType(RecallDocument document, Set<RecallDocumentType> types) {
		return types == null || types.isEmpty() || types.contains(document.type());
	}

	private static RecallDocumentType parseType(Object rawType) {
		if (rawType == null) {
			return RecallDocumentType.DOCUMENT;
		}
		try {
			return RecallDocumentType.valueOf(String.valueOf(rawType).trim().toUpperCase());
		}
		catch (IllegalArgumentException ex) {
			return RecallDocumentType.DOCUMENT;
		}
	}

	private static double numberValue(Object raw) {
		return raw instanceof Number number ? number.doubleValue() : 0;
	}

	private static String stringValue(Object raw) {
		return raw == null ? "" : String.valueOf(raw);
	}

	private static String formatCandidatePreview(String id, Object rawType, double score) {
		return "{id=%s,type=%s,score=%.4f}".formatted(id, stringValue(rawType), score);
	}

	private static String toVectorLiteral(List<Double> vector) {
		if (vector == null || vector.isEmpty()) {
			throw new IllegalArgumentException("Vector must not be empty");
		}
		StringBuilder builder = new StringBuilder("[");
		for (int i = 0; i < vector.size(); i++) {
			if (i > 0) {
				builder.append(',');
			}
			builder.append(Double.toString(vector.get(i)));
		}
		return builder.append(']').toString();
	}

}
