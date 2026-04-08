package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
@Order(50)
@ConditionalOnProperty(name = "search.lite.sql.execute.provider", havingValue = "mock", matchIfMissing = true)
public class SqlExecuteMockStep implements SearchLiteStep {

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.SQL_EXECUTE;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		String sql = state.getSql();
		if (sql == null || sql.isBlank()) {
			sql = "SELECT 'hello' AS greeting, 1 AS value";
			state.setSql(sql);
		}

		List<Map<String, Object>> rows = List.of(Map.of("greeting", "hello", "value", 1));
		state.setRows(rows);
		state.setError(null);
		state.setSqlRetryReason(null);

		Flux<SearchLiteMessage> messages = Flux.just(
				SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在生成并执行 SQL...", null),
				SearchLiteMessages.message(context, stage(), SearchLiteMessageType.SQL, sql, Map.of("sql", sql)),
				SearchLiteMessages.message(context, stage(), SearchLiteMessageType.RESULT_SET, null,
						Map.of("columns", List.of("greeting", "value"), "rows", rows)))
			.delayElements(Duration.ofMillis(150));

		return new SearchLiteStepResult(messages, Mono.just(state));
	}

}
