package com.alibaba.cloud.ai.dataagentbackend.lite.recall.chroma;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocument;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocumentType;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallEmbeddings;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallHit;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallMetadataMatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallOptions;
import com.alibaba.cloud.ai.dataagentbackend.lite.recall.embedding.EmbeddingClient;
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

@Component
@EnableConfigurationProperties(ChromaProperties.class)
public class ChromaVectorSearchService {

	private static final Logger log = LoggerFactory.getLogger(ChromaVectorSearchService.class);

	private final ChromaProperties properties;

	private final EmbeddingClient embeddingClient;

	private final WebClient webClient;

	private volatile String collectionId;

	public ChromaVectorSearchService(ChromaProperties properties, EmbeddingClient embeddingClient, WebClient.Builder webClientBuilder) {
		this.properties = Objects.requireNonNull(properties, "properties");
		this.embeddingClient = Objects.requireNonNull(embeddingClient, "embeddingClient");
		this.webClient = webClientBuilder.baseUrl(trimTrailingSlash(properties.baseUrl()))
			.defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
			.build();
	}

	public boolean isEnabled() {
		return properties.enabled();
	}

	public List<RecallHit> search(String query, List<RecallDocument> documents, RecallOptions options) {
		if (!isEnabled() || documents == null || documents.isEmpty()) {
			return List.of();
		}
		RecallOptions effectiveOptions = options == null ? RecallOptions.defaults() : options;
		List<Double> queryEmbedding = embeddingClient.embed(query);
		if (queryEmbedding.isEmpty()) {
			return List.of();
		}
		String currentCollectionId = ensureCollectionId();
		if (properties.syncOnSearch()) {
			syncDocuments(currentCollectionId, documents);
		}
		Map<String, RecallDocument> originalById = new LinkedHashMap<>();
		for (RecallDocument document : documents) {
			originalById.put(document.id(), document);
		}
		int nResults = Math.max(effectiveOptions.topK() * 5, effectiveOptions.topK() + 10);
		nResults = Math.min(Math.max(nResults, effectiveOptions.topK()), documents.size());
		ChromaQueryResponse response = webClient.post()
			.uri(collectionUri(currentCollectionId, "query"))
			.headers(this::applyAuthHeader)
			.bodyValue(new QueryRequest(List.of(queryEmbedding), null, List.of("documents", "metadatas", "distances"), nResults))
			.retrieve()
			.bodyToMono(ChromaQueryResponse.class)
			.block();
		if (response == null || response.ids() == null || response.ids().isEmpty()) {
			return List.of();
		}
		List<String> ids = response.ids().get(0);
		List<Map<String, Object>> metadatas = firstOrEmpty(response.metadatas());
		List<String> contents = firstOrEmpty(response.documents());
		List<Double> distances = firstOrEmpty(response.distances());
		List<RecallHit> hits = new ArrayList<>();
		for (int i = 0; i < ids.size(); i++) {
			String id = ids.get(i);
			RecallDocument original = originalById.get(id);
			Map<String, Object> metadata = i < metadatas.size() && metadatas.get(i) != null ? metadatas.get(i) : Map.of();
			RecallDocument document = original != null ? mergeDocument(original, metadata)
					: rebuildDocument(id, i < contents.size() ? contents.get(i) : "", metadata);
			if (!matchesType(document, effectiveOptions.types())
					|| !RecallMetadataMatcher.matches(document, effectiveOptions.requiredMetadata())) {
				continue;
			}
			double distance = i < distances.size() && distances.get(i) != null ? distances.get(i) : Double.MAX_VALUE;
			double score = toSimilarity(distance);
			if (score > 0) {
				hits.add(new RecallHit(document, score, List.of("chroma")));
			}
		}
		return hits.stream()
			.sorted(Comparator.comparingDouble(RecallHit::score).reversed())
			.limit(effectiveOptions.topK())
			.toList();
	}

	private void syncDocuments(String currentCollectionId, List<RecallDocument> documents) {
		List<RecallDocument> withEmbeddings = documents.stream()
			.filter(RecallEmbeddings::hasEmbedding)
			.toList();
		if (withEmbeddings.isEmpty()) {
			return;
		}
		List<String> ids = withEmbeddings.stream().map(RecallDocument::id).toList();
		webClient.post()
			.uri(collectionUri(currentCollectionId, "delete"))
			.headers(this::applyAuthHeader)
			.bodyValue(Map.of("ids", ids))
			.retrieve()
			.bodyToMono(String.class)
			.onErrorResume(ex -> {
				log.debug("chroma delete-before-add skipped: {}", ex.getMessage());
				return reactor.core.publisher.Mono.empty();
			})
			.block();
		List<List<Double>> embeddings = withEmbeddings.stream().map(RecallEmbeddings::embedding).toList();
		List<String> contents = withEmbeddings.stream().map(RecallDocument::content).toList();
		List<Map<String, Object>> metadatas = withEmbeddings.stream().map(this::toChromaMetadata).toList();
		webClient.post()
			.uri(collectionUri(currentCollectionId, "add"))
			.headers(this::applyAuthHeader)
			.bodyValue(new AddRequest(ids, embeddings, metadatas, contents))
			.retrieve()
			.bodyToMono(String.class)
			.block();
	}

	private String ensureCollectionId() {
		String cached = collectionId;
		if (cached != null && !cached.isBlank()) {
			return cached;
		}
		synchronized (this) {
			if (collectionId != null && !collectionId.isBlank()) {
				return collectionId;
			}
			CollectionResponse response = webClient.post()
				.uri("/api/v2/tenants/{tenant}/databases/{database}/collections", properties.tenant(), properties.database())
				.headers(this::applyAuthHeader)
				.bodyValue(Map.of("name", properties.collectionName(), "get_or_create", true))
				.retrieve()
				.bodyToMono(CollectionResponse.class)
				.block();
			if (response == null || response.id() == null || response.id().isBlank()) {
				throw new IllegalStateException("Failed to create or resolve Chroma collection id");
			}
			collectionId = response.id();
			return collectionId;
		}
	}

	private RecallDocument mergeDocument(RecallDocument original, Map<String, Object> metadata) {
		Map<String, Object> merged = new LinkedHashMap<>(original.metadata());
		merged.putAll(fromChromaMetadata(metadata));
		return new RecallDocument(original.id(), original.type(), original.title(), original.content(), merged);
	}

	private RecallDocument rebuildDocument(String id, String content, Map<String, Object> metadata) {
		Map<String, Object> restored = fromChromaMetadata(metadata);
		String title = stringValue(restored.getOrDefault("title", id));
		RecallDocumentType type = parseType(restored.get("recallType"));
		return new RecallDocument(id, type, title, content == null ? "" : content, restored);
	}

	private Map<String, Object> toChromaMetadata(RecallDocument document) {
		Map<String, Object> metadata = new LinkedHashMap<>();
		metadata.put("recallType", document.type().name());
		metadata.put("title", document.title());
		for (Map.Entry<String, Object> entry : RecallEmbeddings.publicMetadata(document.metadata()).entrySet()) {
			Object value = normalizeMetadataValue(entry.getValue());
			if (value != null) {
				metadata.put(entry.getKey(), value);
			}
		}
		return metadata;
	}

	private Map<String, Object> fromChromaMetadata(Map<String, Object> metadata) {
		if (metadata == null || metadata.isEmpty()) {
			return Map.of();
		}
		Map<String, Object> restored = new LinkedHashMap<>(metadata);
		restored.remove("title");
		restored.remove("recallType");
		return restored;
	}

	private Object normalizeMetadataValue(Object value) {
		if (value == null) {
			return null;
		}
		if (value instanceof String || value instanceof Number || value instanceof Boolean) {
			return value;
		}
		if (value instanceof Enum<?> enumValue) {
			return enumValue.name();
		}
		if (value instanceof Collection<?> collection) {
			List<Object> normalized = collection.stream()
				.map(this::normalizeMetadataValue)
				.filter(Objects::nonNull)
				.toList();
			return normalized.isEmpty() ? null : normalized;
		}
		return String.valueOf(value);
	}

	private void applyAuthHeader(HttpHeaders headers) {
		if (!properties.token().isBlank()) {
			headers.set("x-chroma-token", properties.token());
		}
	}

	private String collectionUri(String currentCollectionId, String action) {
		return "/api/v2/tenants/%s/databases/%s/collections/%s/%s".formatted(properties.tenant(), properties.database(),
				currentCollectionId, action);
	}

	private static String trimTrailingSlash(String value) {
		if (value == null || value.isBlank()) {
			return "http://localhost:8000";
		}
		String normalized = value.trim();
		return normalized.endsWith("/") ? normalized.substring(0, normalized.length() - 1) : normalized;
	}

	private static boolean matchesType(RecallDocument document, Set<RecallDocumentType> types) {
		return types == null || types.isEmpty() || types.contains(document.type());
	}

	private static double toSimilarity(double distance) {
		if (!Double.isFinite(distance) || distance < 0) {
			return 0;
		}
		return 1.0 / (1.0 + distance);
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

	private static String stringValue(Object value) {
		return value == null ? "" : String.valueOf(value);
	}

	private static <T> List<T> firstOrEmpty(List<List<T>> nested) {
		if (nested == null || nested.isEmpty() || nested.get(0) == null) {
			return List.of();
		}
		return nested.get(0);
	}

	private record QueryRequest(List<List<Double>> query_embeddings, Map<String, Object> where, List<String> include,
			Integer n_results) {
	}

	private record AddRequest(List<String> ids, List<List<Double>> embeddings, List<Map<String, Object>> metadatas,
			List<String> documents) {
	}

	@JsonIgnoreProperties(ignoreUnknown = true)
	private record CollectionResponse(String id, String name) {
	}

	@JsonIgnoreProperties(ignoreUnknown = true)
	private record ChromaQueryResponse(List<List<String>> ids, @JsonAlias("documents") List<List<String>> documents,
			@JsonAlias("metadatas") List<List<Map<String, Object>>> metadatas,
			@JsonAlias("distances") List<List<Double>> distances) {
	}

}
