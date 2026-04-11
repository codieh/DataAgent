package com.alibaba.cloud.ai.dataagentbackend.lite;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;

import java.util.List;

public record SearchLiteRunResult(String threadId, SearchLiteState state, List<SearchLiteMessage> messages,
		long durationMs) {
}
