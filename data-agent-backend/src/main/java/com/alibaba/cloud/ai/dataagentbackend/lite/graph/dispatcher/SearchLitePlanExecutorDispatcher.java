package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLANNER_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PREPARE_RESULT_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.SQL_GENERATE_NODE;

@Component
public class SearchLitePlanExecutorDispatcher implements EdgeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLitePlanExecutorDispatcher.class);

	private final int maxRepairAttempts;

	public SearchLitePlanExecutorDispatcher(
			@Value("${search.lite.graph.planner.max-repair-attempts:2}") int maxRepairAttempts) {
		this.maxRepairAttempts = Math.max(0, maxRepairAttempts);
	}

	@Override
	public String apply(OverAllState state) {
		boolean validationStatus = state.value(SearchLiteGraphStateKeys.PLAN_VALIDATION_STATUS)
			.filter(Boolean.class::isInstance)
			.map(Boolean.class::cast)
			.orElse(true);
		if (!validationStatus) {
			int repairCount = state.value(SearchLiteGraphStateKeys.PLAN_REPAIR_COUNT)
				.filter(Integer.class::isInstance)
				.map(Integer.class::cast)
				.orElse(0);
			if (repairCount > maxRepairAttempts) {
				log.warn("graph plan-executor dispatcher: repair exhausted, route to {}", PREPARE_RESULT_NODE);
				return PREPARE_RESULT_NODE;
			}
			log.info("graph plan-executor dispatcher: validation failed, route to {} for repair, count={}", PLANNER_NODE,
					repairCount);
			return PLANNER_NODE;
		}
		boolean finished = state.value(SearchLiteGraphStateKeys.PLAN_FINISHED)
			.filter(Boolean.class::isInstance)
			.map(Boolean.class::cast)
			.orElse(false);
		if (finished) {
			log.info("graph plan-executor dispatcher: plan finished, route to {}", PREPARE_RESULT_NODE);
			return PREPARE_RESULT_NODE;
		}
		log.info("graph plan-executor dispatcher: route to {}", SQL_GENERATE_NODE);
		return SQL_GENERATE_NODE;
	}

}
