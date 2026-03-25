package com.alibaba.cloud.ai.dataagentbackend.lite.recall.store;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocument;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.List;
import java.util.Optional;

/**
 * 本地文件版检索存储。
 *
 * <p>
 * 先用 JSON 文件把 evidence/schema 索引持久化下来，后续再替换成 PostgreSQL / pgvector。
 * </p>
 */
@Component
public class FileRecallDocumentStore implements RecallDocumentStore {

	private static final Logger log = LoggerFactory.getLogger(FileRecallDocumentStore.class);

	private final ObjectMapper objectMapper;

	private final Path evidencePath;

	private final Path schemaPath;

	private final Path baseDir;

	public FileRecallDocumentStore(ObjectMapper objectMapper,
			@Value("${search.lite.recall.store.dir:./data/recall}") String storeDir) {
		this.objectMapper = objectMapper;
		Path baseDir = Path.of(storeDir).toAbsolutePath().normalize();
		this.baseDir = baseDir;
		this.evidencePath = baseDir.resolve("evidence-index.json");
		this.schemaPath = baseDir.resolve("schema-index.json");
		ensureParent(baseDir);
	}

	@Override
	public void saveEvidenceDocuments(List<RecallDocument> documents) {
		writeJson(evidencePath, documents == null ? List.of() : documents);
	}

	@Override
	public List<RecallDocument> loadEvidenceDocuments() {
		if (!Files.exists(evidencePath)) {
			return List.of();
		}
		try {
			return objectMapper.readValue(evidencePath.toFile(), new TypeReference<List<RecallDocument>>() {
			});
		}
		catch (Exception e) {
			log.warn("加载 evidence 索引失败：path={}, error={}", evidencePath, e.getMessage());
			return List.of();
		}
	}

	@Override
	public void saveSchemaIndex(PersistedSchemaIndex schemaIndex) {
		writeJson(schemaPath, schemaIndex == null ? new PersistedSchemaIndex(List.of(), "", List.of(), List.of()) : schemaIndex);
	}

	@Override
	public Optional<PersistedSchemaIndex> loadSchemaIndex() {
		if (!Files.exists(schemaPath)) {
			return Optional.empty();
		}
		try {
			PersistedSchemaIndex snapshot = objectMapper.readValue(schemaPath.toFile(), PersistedSchemaIndex.class);
			return snapshot == null || snapshot.isEmpty() ? Optional.empty() : Optional.of(snapshot);
		}
		catch (Exception e) {
			log.warn("加载 schema 索引失败：path={}, error={}", schemaPath, e.getMessage());
			return Optional.empty();
		}
	}

	@Override
	public RecallIndexStatus status() {
		List<RecallDocument> evidenceDocuments = loadEvidenceDocuments();
		Optional<PersistedSchemaIndex> schemaIndex = loadSchemaIndex();
		return new RecallIndexStatus(baseDir.toString(), fileStatus(evidencePath, evidenceDocuments.size()),
				fileStatus(schemaPath, schemaIndex.map(index -> index.schemaTables().size()).orElse(0)));
	}

	private void writeJson(Path path, Object value) {
		try {
			ensureParent(path.getParent());
			objectMapper.writerWithDefaultPrettyPrinter().writeValue(path.toFile(), value);
		}
		catch (Exception e) {
			throw new IllegalStateException("写入检索索引失败: " + path, e);
		}
	}

	private static void ensureParent(Path dir) {
		try {
			Files.createDirectories(dir);
		}
		catch (IOException e) {
			throw new IllegalStateException("创建检索索引目录失败: " + dir, e);
		}
	}

	private static RecallFileStatus fileStatus(Path path, int count) {
		if (!Files.exists(path)) {
			return new RecallFileStatus(path.toString(), false, 0L, 0L, count);
		}
		try {
			FileTime lastModified = Files.getLastModifiedTime(path);
			return new RecallFileStatus(path.toString(), true, Files.size(path), lastModified.toMillis(), count);
		}
		catch (IOException e) {
			throw new IllegalStateException("读取检索索引状态失败: " + path, e);
		}
	}

}
