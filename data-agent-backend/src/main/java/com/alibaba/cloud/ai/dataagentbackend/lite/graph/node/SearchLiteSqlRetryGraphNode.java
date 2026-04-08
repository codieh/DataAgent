package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateMapper;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
public class SearchLiteSqlRetryGraphNode implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteSqlRetryGraphNode.class);

	@Override
	public Map<String, Object> apply(OverAllState state) {
		SearchLiteState liteState = SearchLiteGraphStateMapper.toSearchLiteState(state);
		String failedSql = liteState.getSql();
		String error = liteState.getError();
		liteState.setLastFailedSql(failedSql);
		liteState.setSqlRetryReason(error);
		liteState.setSqlRetryCount(liteState.getSqlRetryCount() + 1);
		liteState.setError(null);
		liteState.setResultSummary(null);
		liteState.setRows(java.util.List.of());
		log.info("graph sql-retry node invoked: retryCount={}, reason={}", liteState.getSqlRetryCount(), error);
		return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
	}

}
