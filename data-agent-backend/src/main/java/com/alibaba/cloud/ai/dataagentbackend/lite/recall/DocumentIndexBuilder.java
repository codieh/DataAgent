package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.springframework.stereotype.Component;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

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
		String topic = inferTopic(sourceDocument);
		List<String> tags = inferTags(sourceDocument, topic);
		String docType = inferDocType(sourceDocument);
		metadata.put("sourceType", "document");
		metadata.put("docId", sourceDocument.id());
		metadata.put("docName", sourceDocument.docName());
		metadata.put("sectionTitle", sourceDocument.sectionTitle());
		metadata.put("chunkIndex", sourceDocument.chunkIndex());
		metadata.put("relativePath", sourceDocument.relativePath().toString().replace('\\', '/'));
		metadata.put("fileType", sourceDocument.fileType());
		metadata.put("topic", topic);
		metadata.put("tags", tags);
		metadata.put("docType", docType);

		String title = sourceDocument.sectionTitle().isBlank()
				? sourceDocument.docName()
				: sourceDocument.docName() + " / " + sourceDocument.sectionTitle();

		return new RecallDocument(sourceDocument.id(), RecallDocumentType.DOCUMENT, title, sourceDocument.content(), metadata);
	}

	private String inferTopic(SourceDocument sourceDocument) {
		String pathText = (sourceDocument.docName() + " " + sourceDocument.sectionTitle() + " " + sourceDocument.relativePath())
				.toLowerCase(Locale.ROOT);
		String contentText = sourceDocument.content().toLowerCase(Locale.ROOT);
		if (containsAny(pathText, "inventory", "库存", "补货", "缺货")) {
			return "inventory";
		}
		if (containsAny(pathText, "category", "categories", "分类", "类目", "品类")) {
			return "category";
		}
		if (containsAny(pathText, "product", "products", "商品", "产品", "sku")) {
			return "product";
		}
		if (containsAny(pathText, "order", "orders", "订单", "成交单", "支付单")) {
			return "order";
		}
		if (containsAny(pathText, "gmv", "sales", "metric", "销售额", "成交额", "销量", "营收")) {
			return "sales";
		}
		if (containsAny(contentText, "高消费用户", "高价值用户", "用户分层", "活跃用户", "新用户", "用户消费")) {
			return "user";
		}
		if (containsAny(contentText, "库存", "补货", "缺货")) {
			return "inventory";
		}
		if (containsAny(contentText, "分类", "类目", "品类")) {
			return "category";
		}
		if (containsAny(contentText, "商品", "产品", "sku")) {
			return "product";
		}
		if (containsAny(contentText, "订单", "成交单", "支付单")) {
			return "order";
		}
		if (containsAny(contentText, "高消费", "消费", "gmv", "销售额", "成交额", "销量", "营收", "支付")) {
			return "sales";
		}
		if (containsAny(contentText, "用户", "会员", "人群")) {
			return "user";
		}
		return "general";
	}

	private List<String> inferTags(SourceDocument sourceDocument, String topic) {
		Set<String> tags = new LinkedHashSet<>();
		if (!topic.isBlank()) {
			tags.add(topic);
		}
		String searchable = (sourceDocument.docName() + " " + sourceDocument.sectionTitle() + " " + sourceDocument.content()
				+ " " + sourceDocument.relativePath()).toLowerCase(Locale.ROOT);
		if (containsAny(searchable, "faq", "q:", "a:")) {
			tags.add("faq");
		}
		if (containsAny(searchable, "定义", "definition")) {
			tags.add("definition");
		}
		if (containsAny(searchable, "规则", "rule")) {
			tags.add("rule");
		}
		if (containsAny(searchable, "高消费", "高价值", "消费")) {
			tags.add("consumption");
		}
		return List.copyOf(tags);
	}

	private String inferDocType(SourceDocument sourceDocument) {
		String searchable = (sourceDocument.docName() + " " + sourceDocument.relativePath()).toLowerCase(Locale.ROOT);
		if (containsAny(searchable, "faq")) {
			return "faq";
		}
		if (containsAny(searchable, "definition", "定义")) {
			return "definition";
		}
		if (containsAny(searchable, "rule", "rules", "业务规则")) {
			return "rule";
		}
		if (containsAny(searchable, "metric", "metrics", "指标")) {
			return "metric";
		}
		return "document";
	}

	private boolean containsAny(String text, String... keywords) {
		for (String keyword : keywords) {
			if (text.contains(keyword.toLowerCase(Locale.ROOT))) {
				return true;
			}
		}
		return false;
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
