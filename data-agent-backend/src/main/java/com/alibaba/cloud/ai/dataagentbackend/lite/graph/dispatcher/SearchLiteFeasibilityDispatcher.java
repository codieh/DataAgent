package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLANNER_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PREPARE_RESULT_NODE;

@Component
public class SearchLiteFeasibilityDispatcher implements EdgeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteFeasibilityDispatcher.class);

	@Override
	public String apply(OverAllState state) {
		String feasibilityResult = state.value(SearchLiteGraphStateKeys.FEASIBILITY_RESULT)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.map(String::trim)
			.orElse("数据分析");

		switch (feasibilityResult) {
			case "需要澄清":
				log.info("graph feasibility dispatcher: need clarification, route to {}", PREPARE_RESULT_NODE);
				return PREPARE_RESULT_NODE;
			case "自由闲聊":
				log.info("graph feasibility dispatcher: free chat, route to {}", PREPARE_RESULT_NODE);
				return PREPARE_RESULT_NODE;
			default:
				log.info("graph feasibility dispatcher: data analysis, route to {}", PLANNER_NODE);
				return PLANNER_NODE;
		}
	}

}
