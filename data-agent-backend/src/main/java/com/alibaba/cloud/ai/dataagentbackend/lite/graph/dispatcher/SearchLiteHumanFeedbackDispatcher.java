package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import static com.alibaba.cloud.ai.graph.StateGraph.END;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLAN_EXECUTOR_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLANNER_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.SQL_GENERATE_NODE;

@Component
public class SearchLiteHumanFeedbackDispatcher implements EdgeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteHumanFeedbackDispatcher.class);

	@Override
	public String apply(OverAllState state) {
		String nextNode = state.value(SearchLiteGraphStateKeys.HUMAN_NEXT_NODE)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.orElse("");
		if ("WAIT_FOR_FEEDBACK".equalsIgnoreCase(nextNode)) {
			log.info("graph human-feedback dispatcher: waiting for feedback, route to {}", END);
			return END;
		}
		if ("END".equalsIgnoreCase(nextNode)) {
			log.info("graph human-feedback dispatcher: explicit end requested");
			return END;
		}
		if (PLANNER_NODE.equals(nextNode)) {
			log.info("graph human-feedback dispatcher: rejected, route to {}", PLANNER_NODE);
			return PLANNER_NODE;
		}
		if (PLAN_EXECUTOR_NODE.equals(nextNode)) {
			log.info("graph human-feedback dispatcher: approved, route to {}", PLAN_EXECUTOR_NODE);
			return PLAN_EXECUTOR_NODE;
		}
		if (SQL_GENERATE_NODE.equals(nextNode)) {
			log.info("graph human-feedback dispatcher: approved, route to {}", SQL_GENERATE_NODE);
			return SQL_GENERATE_NODE;
		}
		log.info("graph human-feedback dispatcher: nextNode='{}', default route to {}", nextNode, PLAN_EXECUTOR_NODE);
		return PLAN_EXECUTOR_NODE;
	}

}
