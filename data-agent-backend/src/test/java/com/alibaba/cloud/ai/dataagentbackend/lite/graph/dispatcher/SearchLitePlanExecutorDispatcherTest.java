package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLANNER_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PREPARE_RESULT_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.SQL_GENERATE_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_REPAIR_COUNT;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_FINISHED;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.PLAN_VALIDATION_STATUS;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLitePlanExecutorDispatcherTest {

	private final SearchLitePlanExecutorDispatcher dispatcher = new SearchLitePlanExecutorDispatcher(2);

	@Test
	void should_route_to_sql_generate_when_plan_is_not_finished() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(PLAN_VALIDATION_STATUS)).thenReturn(Optional.of(true));
		when(state.value(PLAN_FINISHED)).thenReturn(Optional.of(false));

		assertEquals(SQL_GENERATE_NODE, dispatcher.apply(state));
	}

	@Test
	void should_route_to_prepare_result_when_plan_is_finished() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(PLAN_VALIDATION_STATUS)).thenReturn(Optional.of(true));
		when(state.value(PLAN_FINISHED)).thenReturn(Optional.of(true));

		assertEquals(PREPARE_RESULT_NODE, dispatcher.apply(state));
	}

	@Test
	void should_route_back_to_planner_when_validation_failed_and_repair_available() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(PLAN_VALIDATION_STATUS)).thenReturn(Optional.of(false));
		when(state.value(PLAN_REPAIR_COUNT)).thenReturn(Optional.of(1));

		assertEquals(PLANNER_NODE, dispatcher.apply(state));
	}

}
