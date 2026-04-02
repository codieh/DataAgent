package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteIntentDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteContinueGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteEvidenceGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteEnhanceGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteIntentGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteResultGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSchemaGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSchemaRecallGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSqlGenerateGraphNode;
import com.alibaba.cloud.ai.graph.KeyStrategy;
import com.alibaba.cloud.ai.graph.KeyStrategyFactory;
import com.alibaba.cloud.ai.graph.StateGraph;
import com.alibaba.cloud.ai.graph.exception.GraphStateException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import static com.alibaba.cloud.ai.graph.action.AsyncEdgeAction.edge_async;
import static com.alibaba.cloud.ai.graph.action.AsyncNodeAction.node_async;
import static com.alibaba.cloud.ai.graph.StateGraph.END;
import static com.alibaba.cloud.ai.graph.StateGraph.START;

@Configuration
public class SearchLiteGraphConfiguration {

	public static final String SEARCH_LITE_GRAPH_NAME = "searchLiteGraph";

	public static final String INTENT_NODE = "intentNode";

	public static final String CONTINUE_NODE = "continueNode";

	public static final String EVIDENCE_NODE = "evidenceNode";

	public static final String SCHEMA_NODE = "schemaNode";

	public static final String SCHEMA_RECALL_NODE = "schemaRecallNode";

	public static final String ENHANCE_NODE = "enhanceNode";

	public static final String SQL_GENERATE_NODE = "sqlGenerateNode";

	public static final String RESULT_NODE = "resultNode";

	@Bean
	public StateGraph searchLiteGraph(SearchLiteIntentGraphNode intentNode, SearchLiteContinueGraphNode continueNode,
			SearchLiteEvidenceGraphNode evidenceNode, SearchLiteSchemaGraphNode schemaNode,
			SearchLiteSchemaRecallGraphNode schemaRecallNode, SearchLiteEnhanceGraphNode enhanceNode,
			SearchLiteSqlGenerateGraphNode sqlGenerateNode,
			SearchLiteResultGraphNode resultNode)
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
			strategies.put(SearchLiteGraphStateKeys.GRAPH_MESSAGES, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.GRAPH_ROUTE, KeyStrategy.REPLACE);
			return strategies;
		};

		StateGraph graph = new StateGraph(SEARCH_LITE_GRAPH_NAME, keyStrategyFactory)
			.addNode(INTENT_NODE, node_async(intentNode))
			.addNode(CONTINUE_NODE, node_async(continueNode))
			.addNode(EVIDENCE_NODE, node_async(evidenceNode))
			.addNode(SCHEMA_NODE, node_async(schemaNode))
			.addNode(SCHEMA_RECALL_NODE, node_async(schemaRecallNode))
			.addNode(ENHANCE_NODE, node_async(enhanceNode))
			.addNode(SQL_GENERATE_NODE, node_async(sqlGenerateNode))
			.addNode(RESULT_NODE, node_async(resultNode));

		graph.addEdge(START, INTENT_NODE)
			.addConditionalEdges(INTENT_NODE, edge_async(new SearchLiteIntentDispatcher()),
					Map.of(EVIDENCE_NODE, EVIDENCE_NODE, END, END))
			.addEdge(EVIDENCE_NODE, SCHEMA_NODE)
			.addEdge(SCHEMA_NODE, SCHEMA_RECALL_NODE)
			.addEdge(SCHEMA_RECALL_NODE, ENHANCE_NODE)
			.addEdge(ENHANCE_NODE, SQL_GENERATE_NODE)
			.addEdge(SQL_GENERATE_NODE, CONTINUE_NODE)
			.addEdge(CONTINUE_NODE, END);
		return graph;
	}

	@Bean(destroyMethod = "shutdown")
	public ExecutorService searchLiteGraphExecutor() {
		return Executors.newFixedThreadPool(4, runnable -> {
			Thread thread = new Thread(runnable);
			thread.setName("search-lite-graph-" + thread.getId());
			thread.setDaemon(true);
			return thread;
		});
	}

}
