package com.alibaba.cloud.ai.dataagentbackend.api;

import java.time.Instant;

public record StreamMessage(String threadId, String type, String message, long seq, Instant timestamp) {
}

