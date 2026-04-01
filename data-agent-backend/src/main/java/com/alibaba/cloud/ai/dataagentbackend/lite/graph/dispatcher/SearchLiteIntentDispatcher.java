package com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphStateKeys;
import com.alibaba.cloud.ai.graph.OverAllState;
import com.alibaba.cloud.ai.graph.action.EdgeAction;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Optional;

import static com.alibaba.cloud.ai.dataagentbackend.lite.graph.SearchLiteGraphConfiguration.RESULT_NODE;
import static com.alibaba.cloud.ai.graph.StateGraph.END;

public class SearchLiteIntentDispatcher implements EdgeAction {

	private static final Logger log = LoggerFactory.getLogger(SearchLiteIntentDispatcher.class);

	@Override
	public String apply(OverAllState state) {
		String classification = state.value(SearchLiteGraphStateKeys.INTENT_CLASSIFICATION)
			.filter(String.class::isInstance)
			.map(String.class::cast)
			.map(String::trim)
			.orElse("");

		if ("DATA_ANALYSIS".equalsIgnoreCase(classification)) {
			log.info("graph intent dispatcher: classified as data analysis, route to {}", RESULT_NODE);
			return RESULT_NODE;
		}

		log.info("graph intent dispatcher: classified as {}, route to END", normalize(classification));
		return END;
	}

	private static String normalize(String classification) {
		return Optional.ofNullable(classification).filter(value -> !value.isBlank()).orElse("<empty>");
	}

}
