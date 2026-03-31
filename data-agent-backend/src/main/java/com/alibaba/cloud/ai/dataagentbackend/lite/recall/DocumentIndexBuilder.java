package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.springframework.stereotype.Component;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * 将本地文档转换为统一的 recall 文档。
 *
 * <p>
 * Step 5.1 先只建立 DOCUMENT 类型与索引入口，文档切块策略在后续步骤继续细化。
 * 当前版本先按“每个文件一个文档”做最小可用实现。
 * </p>
 */
@Component
public class DocumentIndexBuilder {

	public List<RecallDocument> build(List<SourceDocument> sourceDocuments) {
		if (sourceDocuments == null || sourceDocuments.isEmpty()) {
			return List.of();
		}

		List<RecallDocument> documents = new ArrayList<>();
		for (SourceDocument sourceDocument : sourceDocuments) {
			if (sourceDocument == null || sourceDocument.id() == null || sourceDocument.id().isBlank()) {
				continue;
			}
			documents.add(toDocument(sourceDocument));
		}
		return List.copyOf(documents);
	}

	private RecallDocument toDocument(SourceDocument sourceDocument) {
		Map<String, Object> metadata = new LinkedHashMap<>();
		metadata.put("sourceType", "document");
		metadata.put("docId", sourceDocument.id());
		metadata.put("docName", sourceDocument.docName());
		metadata.put("sectionTitle", sourceDocument.sectionTitle());
		metadata.put("chunkIndex", sourceDocument.chunkIndex());
		metadata.put("relativePath", sourceDocument.relativePath().toString().replace('\\', '/'));
		metadata.put("fileType", sourceDocument.fileType());

		String title = sourceDocument.sectionTitle().isBlank()
				? sourceDocument.docName()
				: sourceDocument.docName() + " / " + sourceDocument.sectionTitle();

		return new RecallDocument(sourceDocument.id(), RecallDocumentType.DOCUMENT, title, sourceDocument.content(), metadata);
	}

	public record SourceDocument(String id, String docName, String sectionTitle, int chunkIndex, Path relativePath,
			String fileType, String content) {
		public SourceDocument {
			id = Objects.requireNonNull(id, "id");
			docName = docName == null ? "" : docName.trim();
			sectionTitle = sectionTitle == null ? "" : sectionTitle.trim();
			relativePath = Objects.requireNonNull(relativePath, "relativePath");
			fileType = fileType == null ? "" : fileType.trim().toLowerCase();
			content = content == null ? "" : content.trim();
		}
	}

}
