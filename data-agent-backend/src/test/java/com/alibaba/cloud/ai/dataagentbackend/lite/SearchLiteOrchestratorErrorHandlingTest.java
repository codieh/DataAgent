package com.alibaba.cloud.ai.dataagentbackend.lite;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteRequest;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Orchestrator 异常回归：任何 step 抛异常，都应被转换成 RESULT error 消息，而不是让 Flux 直接抛出。
 */
class SearchLiteOrchestratorErrorHandlingTest {

	@Test
	void orchestrator_should_convert_step_exception_to_error_message() {
		SearchLiteStep badStep = new SearchLiteStep() {
			@Override
			public SearchLiteStage stage() {
				return SearchLiteStage.ENHANCE;
			}

			@Override
			public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
				throw new RuntimeException("boom");
			}
		};

		SearchLiteOrchestrator orchestrator = new SearchLiteOrchestrator(List.of(badStep));
		Flux<SearchLiteMessage> flux = orchestrator.stream(new SearchLiteRequest("agent-1", "thread-1", "q"));

		List<SearchLiteMessage> msgs = flux.collectList().block(Duration.ofSeconds(5));
		assertNotNull(msgs);
		assertFalse(msgs.isEmpty());

		SearchLiteMessage last = msgs.get(msgs.size() - 1);
		assertNotNull(last);
		assertEquals(SearchLiteStage.RESULT, last.stage());
		assertTrue(last.done());
		assertNotNull(last.error());
		assertTrue(last.error().contains("boom"));
	}

}

