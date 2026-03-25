package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import java.util.List;
import java.util.Objects;

/**
 * 一次召回命中的结果。
 */
public record RecallHit(RecallDocument document, double score, List<String> matchedTerms) {

	public RecallHit {
		document = Objects.requireNonNull(document, "document");
		matchedTerms = matchedTerms == null ? List.of() : List.copyOf(matchedTerms);
	}

}
