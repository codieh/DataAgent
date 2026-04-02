package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;

import java.util.List;

public record SearchLiteGraphExecutionResult(SearchLiteState state, List<SearchLiteMessage> messages, String route) {
}
