package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.springframework.stereotype.Component;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.RESULT_NODE;

@Component
public class SearchLiteResultModeDispatcher implements EdgeAction {

	@Override
	public String apply(OverAllState state) {
		return RESULT_NODE;
	}

}
