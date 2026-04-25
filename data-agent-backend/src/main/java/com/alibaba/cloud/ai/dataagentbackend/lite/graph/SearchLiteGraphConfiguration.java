package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteIntentDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLitePlanExecutorDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteResultModeDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteSchemaRecallDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteSqlExecuteDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteSqlGenerateDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteEvidenceGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteEnhanceGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteIntentGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLitePlanExecutorGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLitePlannerGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLitePrepareResultGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteResultGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSchemaGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSchemaRecallGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSqlRetryGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSqlExecuteGraphNode;
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

	public static final String EVIDENCE_NODE = "evidenceNode";

	public static final String SCHEMA_NODE = "schemaNode";

	public static final String SCHEMA_RECALL_NODE = "schemaRecallNode";

	public static final String ENHANCE_NODE = "enhanceNode";

	public static final String PLANNER_NODE = "plannerNode";

	public static final String PLAN_EXECUTOR_NODE = "planExecutorNode";

	public static final String SQL_GENERATE_NODE = "sqlGenerateNode";

	public static final String SQL_EXECUTE_NODE = "sqlExecuteNode";

	public static final String SQL_RETRY_NODE = "sqlRetryNode";

	public static final String PREPARE_RESULT_NODE = "prepareResultNode";

	public static final String RESULT_NODE = "resultNode";

	@Bean
	public StateGraph searchLiteGraph(SearchLiteIntentGraphNode intentNode, SearchLiteEvidenceGraphNode evidenceNode,
			SearchLiteSchemaGraphNode schemaNode,
			SearchLiteSchemaRecallGraphNode schemaRecallNode, SearchLiteEnhanceGraphNode enhanceNode,
			SearchLitePlannerGraphNode plannerNode, SearchLitePlanExecutorGraphNode planExecutorNode,
			SearchLiteSqlGenerateGraphNode sqlGenerateNode, SearchLiteSqlExecuteGraphNode sqlExecuteNode,
			SearchLiteSqlRetryGraphNode sqlRetryNode, SearchLitePrepareResultGraphNode prepareResultNode,
			SearchLiteResultGraphNode resultNode, SearchLiteIntentDispatcher intentDispatcher,
			SearchLitePlanExecutorDispatcher planExecutorDispatcher,
			SearchLiteSchemaRecallDispatcher schemaRecallDispatcher, SearchLiteSqlGenerateDispatcher sqlGenerateDispatcher,
			SearchLiteSqlExecuteDispatcher sqlExecuteDispatcher, SearchLiteResultModeDispatcher resultModeDispatcher)
			throws GraphStateException {
		KeyStrategyFactory keyStrategyFactory = () -> {
			HashMap<String, KeyStrategy> strategies = new HashMap<>();
			strategies.put(SearchLiteGraphStateKeys.AGENT_ID, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.THREAD_ID, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.QUERY, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.MULTI_TURN_CONTEXT, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.CONTEXTUALIZED_QUERY, KeyStrategy.REPLACE);
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
			strategies.put(SearchLiteGraphStateKeys.PLAN_STEPS, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.CURRENT_PLAN_STEP_INDEX, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.PLANNER_ENABLED, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.PLAN_FINISHED, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.PLANNER_RAW_OUTPUT, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.PLAN_VALIDATION_STATUS, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.PLAN_VALIDATION_ERROR, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.PLAN_REPAIR_COUNT, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.SQL, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.SQL_RETRY_COUNT, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.LAST_FAILED_SQL, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.SQL_RETRY_REASON, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.ROWS, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.RESULT_SUMMARY, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.RESULT_MODE, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.ERROR, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.GRAPH_MESSAGES, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.GRAPH_ROUTE, KeyStrategy.REPLACE);
			return strategies;
		};

		StateGraph graph = new StateGraph(SEARCH_LITE_GRAPH_NAME, keyStrategyFactory)
			.addNode(INTENT_NODE, node_async(intentNode))
			.addNode(EVIDENCE_NODE, node_async(evidenceNode))
			.addNode(SCHEMA_NODE, node_async(schemaNode))
			.addNode(SCHEMA_RECALL_NODE, node_async(schemaRecallNode))
			.addNode(ENHANCE_NODE, node_async(enhanceNode))
			.addNode(PLANNER_NODE, node_async(plannerNode))
			.addNode(PLAN_EXECUTOR_NODE, node_async(planExecutorNode))
			.addNode(SQL_GENERATE_NODE, node_async(sqlGenerateNode))
			.addNode(SQL_EXECUTE_NODE, node_async(sqlExecuteNode))
			.addNode(SQL_RETRY_NODE, node_async(sqlRetryNode))
			.addNode(PREPARE_RESULT_NODE, node_async(prepareResultNode))
			.addNode(RESULT_NODE, node_async(resultNode));

		graph.addEdge(START, INTENT_NODE)
			.addConditionalEdges(INTENT_NODE, edge_async(intentDispatcher),
					Map.of(EVIDENCE_NODE, EVIDENCE_NODE, END, END))
			.addEdge(EVIDENCE_NODE, SCHEMA_NODE)
			.addEdge(SCHEMA_NODE, SCHEMA_RECALL_NODE)
			.addConditionalEdges(SCHEMA_RECALL_NODE, edge_async(schemaRecallDispatcher),
					Map.of(ENHANCE_NODE, ENHANCE_NODE, PREPARE_RESULT_NODE, PREPARE_RESULT_NODE))
			.addEdge(ENHANCE_NODE, PLANNER_NODE)
			.addEdge(PLANNER_NODE, PLAN_EXECUTOR_NODE)
			.addConditionalEdges(PLAN_EXECUTOR_NODE, edge_async(planExecutorDispatcher),
					Map.of(SQL_GENERATE_NODE, SQL_GENERATE_NODE, PREPARE_RESULT_NODE, PREPARE_RESULT_NODE))
			.addConditionalEdges(SQL_GENERATE_NODE, edge_async(sqlGenerateDispatcher),
					Map.of(SQL_EXECUTE_NODE, SQL_EXECUTE_NODE, PREPARE_RESULT_NODE, PREPARE_RESULT_NODE))
			.addConditionalEdges(SQL_EXECUTE_NODE, edge_async(sqlExecuteDispatcher),
					Map.of(PREPARE_RESULT_NODE, PREPARE_RESULT_NODE, SQL_RETRY_NODE, SQL_RETRY_NODE,
							PLAN_EXECUTOR_NODE, PLAN_EXECUTOR_NODE))
			.addEdge(SQL_RETRY_NODE, SQL_GENERATE_NODE)
			.addConditionalEdges(PREPARE_RESULT_NODE, edge_async(resultModeDispatcher),
					Map.of(RESULT_NODE, RESULT_NODE))
			.addEdge(RESULT_NODE, END);
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
