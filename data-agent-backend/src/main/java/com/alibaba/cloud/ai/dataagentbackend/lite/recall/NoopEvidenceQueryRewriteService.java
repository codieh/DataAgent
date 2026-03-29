package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * 默认实现：不做改写，直接透传原始 query。
 */
@Component
@ConditionalOnProperty(name = "search.lite.evidence.rewrite.provider", havingValue = "none", matchIfMissing = true)
public class NoopEvidenceQueryRewriteService implements EvidenceQueryRewriteService {

	@Override
	public String rewrite(String query) {
		return query == null ? "" : query.trim();
	}

}
