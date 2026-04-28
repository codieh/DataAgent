package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.springframework.stereotype.Component;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLANNER_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PREPARE_RESULT_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.SQL_GENERATE_NODE;

@Component
public class SearchLiteHumanFeedbackDispatcher implements EdgeAction {

	@Override
	public String apply(OverAllState state) {
		boolean awaiting = state.value(SearchLiteGraphStateKeys.AWAITING_HUMAN_FEEDBACK)
			.filter(Boolean.class::isInstance)
			.map(Boolean.class::cast)
			.orElse(false);
		if (awaiting) {
			return PREPARE_RESULT_NODE;
		}

		String feedbackStatus = state.value(SearchLiteGraphStateKeys.HUMAN_FEEDBACK_STATUS)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.orElse("");
		if ("REJECTED".equalsIgnoreCase(feedbackStatus)) {
			return PLANNER_NODE;
		}
		return SQL_GENERATE_NODE;
	}

}
