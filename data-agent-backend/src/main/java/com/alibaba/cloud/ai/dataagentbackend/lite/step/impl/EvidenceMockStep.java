package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.EvidenceItem;
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
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
@Order(20)
public class EvidenceMockStep implements SearchLiteStep {

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.EVIDENCE;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		List<EvidenceItem> evidences = List.of(
				new EvidenceItem("ev-1", "指标口径说明", "GMV 指标口径：支付金额合计（含退款前）...", "mock://kb/metrics", 0.92,
						Map.of("type", "DOC")),
				new EvidenceItem("ev-2", "核心用户定义", "核心用户：近 30 天内完成过支付且退款率 < 5% 的用户...", "mock://kb/users", 0.87,
						Map.of("type", "FAQ")));

		state.setEvidences(evidences);
		state.setEvidenceText("""
				[证据1] GMV 指标口径：支付金额合计（含退款前）
				[证据2] 核心用户：近30天内完成过支付且退款率<5%
				""".trim());

		Flux<SearchLiteMessage> messages = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在召回证据...", null),
					SearchLiteMessages.message(context, stage(), SearchLiteMessageType.JSON, null,
							Map.of("evidences", evidences)))
			.delayElements(Duration.ofMillis(150));

		return new SearchLiteStepResult(messages, Mono.just(state));
	}

}

