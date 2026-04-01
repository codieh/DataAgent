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

	@Bean
	public StateGraph searchLiteGraph(SearchLiteIntentGraphNode intentNode, SearchLiteResultGraphNode resultNode)
			throws GraphStateException {
		KeyStrategyFactory keyStrategyFactory = () -> {
			HashMap<String, KeyStrategy> strategies = new HashMap<>();
			strategies.put(SearchLiteGraphStateKeys.AGENT_ID, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.THREAD_ID, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.QUERY, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.INTENT_CLASSIFICATION, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.EVIDENCES, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.EVIDENCE_TEXT, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.EVIDENCE_REWRITE_QUERY, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.DOCUMENT_TEXT, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.SCHEMA_TABLES, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.SCHEMA_TEXT, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.SCHEMA_TABLE_DETAILS, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.RECALLED_TABLES, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.RECALLED_SCHEMA_TEXT, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.CANONICAL_QUERY, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.EXPANDED_QUERIES, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.SQL, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.ROWS, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.RESULT_SUMMARY, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.ERROR, KeyStrategy.REPLACE);
			return strategies;
		};

		StateGraph graph = new StateGraph(SEARCH_LITE_GRAPH_NAME, keyStrategyFactory)
			.addNode(INTENT_NODE, node_async(intentNode))
			.addNode(RESULT_NODE, node_async(resultNode));

		graph.addEdge(START, INTENT_NODE).addEdge(INTENT_NODE, RESULT_NODE).addEdge(RESULT_NODE, END);
		return graph;
	}

}
