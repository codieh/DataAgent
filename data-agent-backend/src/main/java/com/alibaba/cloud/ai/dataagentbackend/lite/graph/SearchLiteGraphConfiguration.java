package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteIntentGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteResultGraphNode;
import com.alibaba.cloud.ai.graph.KeyStrategy;
import com.alibaba.cloud.ai.graph.KeyStrategyFactory;
import com.alibaba.cloud.ai.graph.StateGraph;
import com.alibaba.cloud.ai.graph.exception.GraphStateException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.HashMap;

import static com.alibaba.cloud.ai.graph.action.AsyncNodeAction.node_async;
import static com.alibaba.cloud.ai.graph.StateGraph.END;
import static com.alibaba.cloud.ai.graph.StateGraph.START;

@Configuration
public class SearchLiteGraphConfiguration {

	public static final String SEARCH_LITE_GRAPH_NAME = "searchLiteGraph";

	public static final String INTENT_NODE = "intentNode";

	public static final String RESULT_NODE = "resultNode";

	public static final String QUERY_KEY = "query";

	public static final String THREAD_ID_KEY = "threadId";

	public static final String INTENT_CLASSIFICATION_KEY = "intentClassification";

	public static final String RESULT_SUMMARY_KEY = "resultSummary";

	@Bean
	public StateGraph searchLiteGraph(SearchLiteIntentGraphNode intentNode, SearchLiteResultGraphNode resultNode)
			throws GraphStateException {
		KeyStrategyFactory keyStrategyFactory = () -> {
			HashMap<String, KeyStrategy> strategies = new HashMap<>();
			strategies.put(QUERY_KEY, KeyStrategy.REPLACE);
			strategies.put(THREAD_ID_KEY, KeyStrategy.REPLACE);
			strategies.put(INTENT_CLASSIFICATION_KEY, KeyStrategy.REPLACE);
			strategies.put(RESULT_SUMMARY_KEY, KeyStrategy.REPLACE);
			return strategies;
		};

		StateGraph graph = new StateGraph(SEARCH_LITE_GRAPH_NAME, keyStrategyFactory)
			.addNode(INTENT_NODE, node_async(intentNode))
			.addNode(RESULT_NODE, node_async(resultNode));

		graph.addEdge(START, INTENT_NODE).addEdge(INTENT_NODE, RESULT_NODE).addEdge(RESULT_NODE, END);
		return graph;
	}

}
