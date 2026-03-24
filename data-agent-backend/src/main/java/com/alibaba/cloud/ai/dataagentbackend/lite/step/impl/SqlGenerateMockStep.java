package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.Map;

/**
 * SQL 生成 mock：用于稳定回归测试（不依赖真实 LLM）。
 */
@Component
@Order(40)
@ConditionalOnProperty(name = "search.lite.sql.generate.provider", havingValue = "mock")
public class SqlGenerateMockStep implements SearchLiteStep {

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.SQL_GENERATE;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		String sql = "SELECT * FROM orders LIMIT 1";
		state.setSql(sql);

		Flux<SearchLiteMessage> messages = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在生成 SQL...", null),
					SearchLiteMessages.message(context, stage(), SearchLiteMessageType.SQL, sql, Map.of("sql", sql, "mock", true)))
			.delayElements(Duration.ofMillis(30));

		return new SearchLiteStepResult(messages, Mono.just(state));
	}

}

