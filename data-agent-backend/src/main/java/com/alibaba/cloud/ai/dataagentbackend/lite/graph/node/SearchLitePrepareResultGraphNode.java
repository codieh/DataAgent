package com.alibaba.cloud.ai.dataagentbackend.lite.graph.node;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateMapper;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.NodeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.Map;

@Component
public class SearchLitePrepareResultGraphNode implements NodeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLitePrepareResultGraphNode.class);

	public static final String MODE_SUCCESS = "success";

	public static final String MODE_NO_SCHEMA = "no_schema";

	public static final String MODE_NO_SQL = "no_sql";

	public static final String MODE_EXECUTION_ERROR = "execution_error";

	@Override
	public Map<String, Object> apply(OverAllState state) {
		SearchLiteState liteState = SearchLiteGraphStateMapper.toSearchLiteState(state);
		if (StringUtils.hasText(liteState.getError())) {
			liteState.setResultMode(MODE_EXECUTION_ERROR);
			if (!StringUtils.hasText(liteState.getResultSummary())) {
				liteState.setResultSummary("SQL 执行失败：" + liteState.getError());
			}
		}
		else if (!hasRecalledTables(liteState)) {
			liteState.setResultMode(MODE_NO_SCHEMA);
			liteState.setError("未找到与当前问题相关的数据表，请补充更明确的业务对象、指标或筛选条件。");
		}
		else if (!StringUtils.hasText(liteState.getSql())) {
			liteState.setResultMode(MODE_NO_SQL);
			liteState.setError("未生成可执行 SQL，请换一种更明确的描述，或拆分问题后重试。");
		}
		else {
			liteState.setResultMode(MODE_SUCCESS);
			liteState.setError(null);
		}
		log.info("graph prepare-result node invoked: mode={}", liteState.getResultMode());
		return SearchLiteGraphStateMapper.fromSearchLiteState(liteState);
	}

	private boolean hasRecalledTables(SearchLiteState state) {
		return state.getRecalledTables() != null && !state.getRecalledTables().isEmpty();
	}

}
