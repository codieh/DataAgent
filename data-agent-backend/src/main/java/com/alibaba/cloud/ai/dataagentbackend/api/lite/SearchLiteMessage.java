package com.alibaba.cloud.ai.dataagentbackend.api.lite;

import java.time.Instant;

public record SearchLiteMessage(String threadId, SearchLiteStage stage, SearchLiteMessageType type, String chunk,
		Object payload, boolean done, String error, long seq, Instant timestamp) {
}

