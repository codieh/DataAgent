package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import java.util.List;

/**
 * 统一召回引擎接口。
 */
public interface RecallEngine {

	List<RecallHit> search(String query, List<RecallDocument> documents, RecallOptions options);

}
