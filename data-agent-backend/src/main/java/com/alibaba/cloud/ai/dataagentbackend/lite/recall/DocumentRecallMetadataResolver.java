package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.springframework.stereotype.Component;

import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * 为 document recall 提供轻量 metadata 过滤策略。
 */
@Component
public class DocumentRecallMetadataResolver {

	private static final List<TopicRule> TOPIC_RULES = List.of(
			new TopicRule("sales", List.of("销售额", "gmv", "成交额", "金额", "销量", "高消费", "消费", "营收", "支付")),
			new TopicRule("user", List.of("用户", "会员", "人群", "高价值用户", "高消费用户", "活跃用户", "新用户")),
			new TopicRule("inventory", List.of("库存", "补货", "缺货")),
			new TopicRule("category", List.of("分类", "类目", "品类")),
			new TopicRule("product", List.of("商品", "产品", "sku")),
			new TopicRule("order", List.of("订单", "下单", "支付单", "成交单")),
			new TopicRule("time", List.of("时间", "最近", "近", "月", "季度", "年度", "天", "周", "趋势")));

	public DocumentRecallFilter resolve(String query) {
		if (query == null || query.isBlank()) {
			return DocumentRecallFilter.empty();
		}
		String lowerQuery = query.toLowerCase(Locale.ROOT);
		boolean userConsumptionQuery = containsAny(lowerQuery, "高消费用户", "高价值用户", "用户消费");
		Set<String> topics = new LinkedHashSet<>();
		Set<String> tags = new LinkedHashSet<>();
		for (TopicRule rule : TOPIC_RULES) {
			for (String keyword : rule.keywords()) {
				if (lowerQuery.contains(keyword.toLowerCase(Locale.ROOT))) {
					if (userConsumptionQuery && "sales".equals(rule.topic())) {
						tags.add("consumption");
						break;
					}
					topics.add(rule.topic());
					tags.add(rule.topic());
					if ("user".equals(rule.topic()) && containsAny(lowerQuery, "高消费", "消费", "高价值")) {
						tags.add("consumption");
					}
					break;
				}
			}
		}
		return new DocumentRecallFilter(List.copyOf(topics), List.copyOf(tags));
	}

	private boolean containsAny(String query, String... keywords) {
		for (String keyword : keywords) {
			if (query.contains(keyword.toLowerCase(Locale.ROOT))) {
				return true;
			}
		}
		return false;
	}

	public record DocumentRecallFilter(List<String> topics, List<String> tags) {
		public DocumentRecallFilter {
			topics = topics == null ? List.of() : List.copyOf(topics);
			tags = tags == null ? List.of() : List.copyOf(tags);
		}

		public boolean isEmpty() {
			return topics.isEmpty() && tags.isEmpty();
		}

		public Map<String, Object> toRequiredMetadata() {
			if (!topics.isEmpty()) {
				return Map.of("topic", topics);
			}
			if (!tags.isEmpty()) {
				return Map.of("tags", tags);
			}
			return Map.of();
		}

		public String summary() {
			if (isEmpty()) {
				return "(none)";
			}
			return "topics=%s,tags=%s".formatted(topics, tags);
		}

		public static DocumentRecallFilter empty() {
			return new DocumentRecallFilter(List.of(), List.of());
		}
	}

	private record TopicRule(String topic, List<String> keywords) {
	}

}
