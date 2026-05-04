package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import java.util.List;

/**
 * Recall 候选重排抽象。
 */
public interface RecallReranker {

	List<RecallHit> rerank(String query, List<RecallHit> candidates, int topK);

}
