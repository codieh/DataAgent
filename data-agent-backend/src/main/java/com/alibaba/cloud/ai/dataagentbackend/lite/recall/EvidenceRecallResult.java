package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;

import java.util.List;

/**
 * Evidence 召回结果。
 */
public record EvidenceRecallResult(List<EvidenceItem> items, String promptText, List<RecallHit> hits) {

	public EvidenceRecallResult {
		items = items == null ? List.of() : List.copyOf(items);
		promptText = promptText == null ? "" : promptText;
		hits = hits == null ? List.of() : List.copyOf(hits);
	}

}
