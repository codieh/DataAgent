package com.alibaba.cloud.ai.dataagentbackend.lite.recall.store;

/**
 * 检索索引整体状态。
 */
public record RecallIndexStatus(String storeDir, RecallFileStatus evidence, RecallFileStatus document,
		RecallFileStatus schema) {
}
