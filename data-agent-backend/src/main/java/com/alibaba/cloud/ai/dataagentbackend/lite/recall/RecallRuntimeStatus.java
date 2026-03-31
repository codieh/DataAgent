package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.lite.recall.store.RecallIndexStatus;

/**
 * 检索运行时状态。
 */
public record RecallRuntimeStatus(RecallIndexStatus index, DocumentSourceStatus documentSource) {
}
