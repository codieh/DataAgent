package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import java.util.Collection;
import java.util.Map;
import java.util.Objects;

/**
 * 统一处理召回时的 metadata 匹配逻辑。
 */
public final class RecallMetadataMatcher {

	private RecallMetadataMatcher() {
	}

	public static boolean matches(RecallDocument document, Map<String, Object> requiredMetadata) {
		if (requiredMetadata == null || requiredMetadata.isEmpty()) {
			return true;
		}
		Map<String, Object> metadata = document.metadata();
		for (Map.Entry<String, Object> entry : requiredMetadata.entrySet()) {
			Object actual = metadata.get(entry.getKey());
			if (!matchesValue(actual, entry.getValue())) {
				return false;
			}
		}
		return true;
	}

	private static boolean matchesValue(Object actual, Object expected) {
		if (actual == null || expected == null) {
			return false;
		}
		if (actual instanceof Collection<?> actualCollection && expected instanceof Collection<?> expectedCollection) {
			return actualCollection.stream().anyMatch(item -> expectedCollection.stream().anyMatch(expect -> equalsItem(item, expect)));
		}
		if (actual instanceof Collection<?> actualCollection) {
			return actualCollection.stream().anyMatch(item -> equalsItem(item, expected));
		}
		if (expected instanceof Collection<?> expectedCollection) {
			return expectedCollection.stream().anyMatch(expect -> equalsItem(actual, expect));
		}
		return equalsItem(actual, expected);
	}

	private static boolean equalsItem(Object actual, Object expected) {
		return Objects.equals(normalize(actual), normalize(expected));
	}

	private static Object normalize(Object value) {
		return value instanceof String text ? text.trim().toLowerCase() : value;
	}

}
