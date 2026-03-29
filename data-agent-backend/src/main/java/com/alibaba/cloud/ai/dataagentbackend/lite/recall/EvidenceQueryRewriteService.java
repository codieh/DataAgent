package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

/**
 * 为 Evidence Recall 提供专用的查询改写能力。
 */
public interface EvidenceQueryRewriteService {

	String rewrite(String query);

}
