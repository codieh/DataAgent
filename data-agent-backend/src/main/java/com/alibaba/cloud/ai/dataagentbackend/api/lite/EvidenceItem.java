package com.alibaba.cloud.ai.dataagentbackend.api.lite;

import java.util.Map;

public record EvidenceItem(String id, String title, String snippet, String source, Double score, Map<String, Object> metadata) {
}

