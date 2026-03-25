package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import java.util.Map;
import java.util.Set;

/**
 * 召回参数。
 */
public record RecallOptions(int topK, Set<RecallDocumentType> types, Map<String, Object> requiredMetadata) {

	public RecallOptions {
		topK = topK <= 0 ? 5 : topK;
		types = types == null ? Set.of() : Set.copyOf(types);
		requiredMetadata = requiredMetadata == null ? Map.of() : Map.copyOf(requiredMetadata);
	}

	public static RecallOptions defaults() {
		return new RecallOptions(5, Set.of(), Map.of());
	}

}
