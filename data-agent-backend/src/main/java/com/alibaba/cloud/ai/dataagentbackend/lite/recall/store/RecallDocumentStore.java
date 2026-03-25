package com.alibaba.cloud.ai.dataagentbackend.lite.recall.store;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.RecallDocument;

import java.util.List;
import java.util.Optional;

/**
 * 检索文档存储接口。
 *
 * <p>
 * 当前先提供本地文件实现，后续可以平滑替换成 PostgreSQL / pgvector。
 * </p>
 */
public interface RecallDocumentStore {

	void saveEvidenceDocuments(List<RecallDocument> documents);

	List<RecallDocument> loadEvidenceDocuments();

	void saveSchemaIndex(PersistedSchemaIndex schemaIndex);

	Optional<PersistedSchemaIndex> loadSchemaIndex();

	RecallIndexStatus status();

}
