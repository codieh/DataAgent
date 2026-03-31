package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

/**
 * 本地文档源状态。
 */
public record DocumentSourceStatus(String dir, boolean exists, int fileCount, int chunkCount) {
}
