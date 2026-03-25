package com.alibaba.cloud.ai.dataagentbackend.lite.recall.store;

/**
 * 单个索引文件状态。
 */
public record RecallFileStatus(String path, boolean exists, long sizeBytes, long lastModifiedEpochMillis, int count) {
}
