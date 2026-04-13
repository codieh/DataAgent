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
import java.util.Map;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
@Order(60)
@ConditionalOnProperty(name = "search.lite.result.provider", havingValue = "mock", matchIfMissing = true)
public class ResultMockStep implements SearchLiteStep {

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.RESULT;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		String summary;
		if ("no_schema".equalsIgnoreCase(state.getResultMode())) {
			summary = "未找到与当前问题相关的数据表，请补充更明确的业务对象或指标后再试。";
		}
		else if ("no_sql".equalsIgnoreCase(state.getResultMode())) {
			summary = "当前问题暂未生成可执行 SQL，请换一种更明确的描述或拆分问题后重试。";
		}
		else if ("execution_error".equalsIgnoreCase(state.getResultMode()) && state.getError() != null
				&& !state.getError().isBlank()) {
			summary = "执行失败：" + state.getError();
		}
		else if ("blocked_sensitive_sql".equalsIgnoreCase(state.getResultMode())) {
			summary = "当前查询涉及敏感字段或敏感明细，已被安全策略拦截。建议改为统计类查询或去除敏感字段后重试。";
		}
		else if ("blocked_wide_export".equalsIgnoreCase(state.getResultMode())) {
			summary = "当前查询可能导致大范围明细导出，已被安全策略拦截。建议增加筛选条件、限制范围，或改为聚合统计后重试。";
		}
		else {
			summary = "执行完成，共返回 " + (state.getRows() == null ? 0 : state.getRows().size()) + " 行数据。";
		}
		state.setResultSummary(summary);

		Flux<SearchLiteMessage> messages = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在整理结果...", null),
					SearchLiteMessages.done(context, stage(), SearchLiteMessageType.JSON, null,
							Map.of("summary", summary, "resultMode",
									state.getResultMode() == null ? "success" : state.getResultMode())))
			.delayElements(Duration.ofMillis(150));

		return new SearchLiteStepResult(messages, Mono.just(state));
	}

}
