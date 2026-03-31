package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import java.util.List;

/**
 * Document 召回结果。
 */
public record DocumentRecallResult(List<RecallDocument> documents, String promptText, List<RecallHit> hits) {

	public DocumentRecallResult {
		documents = documents == null ? List.of() : List.copyOf(documents);
		promptText = promptText == null ? "" : promptText;
		hits = hits == null ? List.of() : List.copyOf(hits);
	}

}
