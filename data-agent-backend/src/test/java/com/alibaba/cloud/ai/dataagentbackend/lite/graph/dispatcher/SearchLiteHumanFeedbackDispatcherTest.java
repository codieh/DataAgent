package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.graph.OverAllState;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PLANNER_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.PREPARE_RESULT_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.SQL_GENERATE_NODE;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.AWAITING_HUMAN_FEEDBACK;
import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys.HUMAN_FEEDBACK_STATUS;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SearchLiteHumanFeedbackDispatcherTest {

	@Test
	void should_route_to_prepare_result_when_waiting_for_feedback() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(AWAITING_HUMAN_FEEDBACK)).thenReturn(Optional.of(true));

		assertEquals(PREPARE_RESULT_NODE, new SearchLiteHumanFeedbackDispatcher().apply(state));
	}

	@Test
	void should_route_to_planner_when_feedback_rejected() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(AWAITING_HUMAN_FEEDBACK)).thenReturn(Optional.of(false));
		when(state.value(HUMAN_FEEDBACK_STATUS)).thenReturn(Optional.of("REJECTED"));

		assertEquals(PLANNER_NODE, new SearchLiteHumanFeedbackDispatcher().apply(state));
	}

	@Test
	void should_route_to_sql_generate_when_feedback_approved() {
		OverAllState state = mock(OverAllState.class);
		when(state.value(anyString())).thenReturn(Optional.empty());
		when(state.value(AWAITING_HUMAN_FEEDBACK)).thenReturn(Optional.of(false));
		when(state.value(HUMAN_FEEDBACK_STATUS)).thenReturn(Optional.of("APPROVED"));

		assertEquals(SQL_GENERATE_NODE, new SearchLiteHumanFeedbackDispatcher().apply(state));
	}

}
