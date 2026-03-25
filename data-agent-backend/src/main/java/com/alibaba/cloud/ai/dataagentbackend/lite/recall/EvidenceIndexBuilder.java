package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Locale;
import java.util.Set;

/**
 * 将 evidence 数据统一转换为可检索文档。
 */
@Component
public class EvidenceIndexBuilder {

	public List<RecallDocument> build(List<EvidenceItem> evidenceItems) {
		if (evidenceItems == null || evidenceItems.isEmpty()) {
			return List.of();
		}

		List<RecallDocument> documents = new ArrayList<>();
		for (EvidenceItem item : evidenceItems) {
			if (item == null || isBlank(item.id())) {
				continue;
			}
			documents.add(toDocument(item));
		}
		return List.copyOf(documents);
	}

	private RecallDocument toDocument(EvidenceItem item) {
		List<String> tags = normalizeTags(item);
		String topic = inferTopic(item, tags);
		Map<String, Object> metadata = new LinkedHashMap<>();
		if (item.metadata() != null && !item.metadata().isEmpty()) {
			metadata.putAll(item.metadata());
		}
		metadata.put("source", safe(item.source()));
		metadata.put("rawScore", item.score());
		metadata.put("snippet", safe(item.snippet()));
		metadata.put("tags", tags);
		metadata.put("topic", topic);

		StringBuilder content = new StringBuilder();
		content.append("标题: ").append(safe(item.title()));
		if (!isBlank(item.snippet())) {
			content.append("，内容: ").append(item.snippet().trim());
		}
		if (!isBlank(item.source())) {
			content.append("，来源: ").append(item.source().trim());
		}

		return new RecallDocument(item.id(), RecallDocumentType.EVIDENCE, safe(item.title()), content.toString(),
				metadata);
	}

	private List<String> normalizeTags(EvidenceItem item) {
		Set<String> tags = new LinkedHashSet<>();
		if (item.metadata() != null) {
			Object rawTags = item.metadata().get("tags");
			if (rawTags instanceof List<?> list) {
				list.stream()
					.filter(String.class::isInstance)
					.map(String.class::cast)
					.map(this::normalize)
					.filter(tag -> !tag.isBlank())
					.forEach(tags::add);
			}
		}
		String inferredTopic = inferTopic(item, List.of());
		if (!inferredTopic.isBlank()) {
			tags.add(inferredTopic);
		}
		return List.copyOf(tags);
	}

	private String inferTopic(EvidenceItem item, List<String> tags) {
		for (String tag : tags) {
			if (List.of("metric", "gmv", "sales").contains(tag)) {
				return "sales";
			}
			if (List.of("user", "core-user").contains(tag)) {
				return "user";
			}
			if (List.of("time", "default").contains(tag)) {
				return "time";
			}
		}
		String searchable = (safe(item.title()) + " " + safe(item.snippet()) + " " + safe(item.source())).toLowerCase(Locale.ROOT);
		if (containsAny(searchable, "销售额", "gmv", "成交额", "销量", "金额", "支付")) {
			return "sales";
		}
		if (containsAny(searchable, "用户", "注册", "活跃", "核心用户")) {
			return "user";
		}
		if (containsAny(searchable, "时间", "最近", "月", "季度", "7 天", "七天")) {
			return "time";
		}
		if (containsAny(searchable, "库存", "补货", "缺货")) {
			return "inventory";
		}
		if (containsAny(searchable, "分类", "类目", "品类")) {
			return "category";
		}
		if (containsAny(searchable, "商品", "产品", "sku")) {
			return "product";
		}
		if (containsAny(searchable, "订单", "支付单", "成交单")) {
			return "order";
		}
		return "general";
	}

	private boolean containsAny(String text, String... keywords) {
		for (String keyword : keywords) {
			if (text.contains(keyword.toLowerCase(Locale.ROOT))) {
				return true;
			}
		}
		return false;
	}

	private String normalize(String text) {
		return text == null ? "" : text.trim().toLowerCase(Locale.ROOT);
	}

	private static boolean isBlank(String text) {
		return text == null || text.isBlank();
	}

	private static String safe(String text) {
		return text == null ? "" : text;
	}

}
