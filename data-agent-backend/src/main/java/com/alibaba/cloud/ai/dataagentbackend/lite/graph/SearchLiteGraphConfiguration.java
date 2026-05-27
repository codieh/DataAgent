package com.alibaba.cloud.ai.dataagentbackend.lite.graph;

import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteFeasibilityDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteIntentDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteHumanFeedbackDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLitePlanExecutorDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteResultModeDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteSchemaRecallDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteSqlConsistencyDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteSqlExecuteDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteSqlGenerateDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.dispatcher.SearchLiteSqlRepairDispatcher;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteEvidenceGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteEnhanceGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteFeasibilityGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteIntentGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteHumanFeedbackGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLitePlanExecutorGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLitePlannerGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLitePrepareResultGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteResultGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSchemaGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSchemaRecallGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSqlConsistencyGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSqlRepairGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSqlRetryGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSqlExecuteGraphNode;
import com.alibaba.cloud.ai.dataagentbackend.lite.graph.node.SearchLiteSqlGenerateGraphNode;
import com.alibaba.cloud.ai.graph.KeyStrategy;
import com.alibaba.cloud.ai.graph.KeyStrategyFactory;
import com.alibaba.cloud.ai.graph.StateGraph;
import com.alibaba.cloud.ai.graph.exception.GraphStateException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;

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

	public static final String FEASIBILITY_NODE = "feasibilityNode";

	public static final String PLANNER_NODE = "plannerNode";

	public static final String PLAN_EXECUTOR_NODE = "planExecutorNode";

	public static final String HUMAN_FEEDBACK_NODE = "humanFeedbackNode";

	public static final String SQL_GENERATE_NODE = "sqlGenerateNode";

	public static final String SQL_CONSISTENCY_NODE = "sqlConsistencyNode";

	public static final String SQL_EXECUTE_NODE = "sqlExecuteNode";

	public static final String SQL_REPAIR_NODE = "sqlRepairNode";

	public static final String SQL_RETRY_NODE = "sqlRetryNode";

	public static final String PREPARE_RESULT_NODE = "prepareResultNode";

	public static final String RESULT_NODE = "resultNode";

	@Bean
	public StateGraph searchLiteGraph(SearchLiteIntentGraphNode intentNode, SearchLiteEvidenceGraphNode evidenceNode,
			SearchLiteSchemaGraphNode schemaNode,
			SearchLiteSchemaRecallGraphNode schemaRecallNode, SearchLiteEnhanceGraphNode enhanceNode,
			SearchLiteFeasibilityGraphNode feasibilityNode,
			SearchLitePlannerGraphNode plannerNode, SearchLitePlanExecutorGraphNode planExecutorNode,
			SearchLiteHumanFeedbackGraphNode humanFeedbackNode,
			SearchLiteSqlGenerateGraphNode sqlGenerateNode, SearchLiteSqlConsistencyGraphNode sqlConsistencyNode,
			SearchLiteSqlExecuteGraphNode sqlExecuteNode, SearchLiteSqlRepairGraphNode sqlRepairNode,
			SearchLiteSqlRetryGraphNode sqlRetryNode, SearchLitePrepareResultGraphNode prepareResultNode,
			SearchLiteResultGraphNode resultNode, SearchLiteIntentDispatcher intentDispatcher,
			SearchLiteFeasibilityDispatcher feasibilityDispatcher,
			SearchLitePlanExecutorDispatcher planExecutorDispatcher, SearchLiteHumanFeedbackDispatcher humanFeedbackDispatcher,
			SearchLiteSchemaRecallDispatcher schemaRecallDispatcher, SearchLiteSqlGenerateDispatcher sqlGenerateDispatcher,
			SearchLiteSqlConsistencyDispatcher sqlConsistencyDispatcher,
			SearchLiteSqlExecuteDispatcher sqlExecuteDispatcher, SearchLiteSqlRepairDispatcher sqlRepairDispatcher,
			SearchLiteResultModeDispatcher resultModeDispatcher)
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
			strategies.put(SearchLiteGraphStateKeys.FEASIBILITY_RESULT, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.FEASIBILITY_MESSAGE, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.HUMAN_REVIEW_ENABLED, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.HUMAN_FEEDBACK_STATUS, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.HUMAN_FEEDBACK_COMMENT, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.HUMAN_FEEDBACK_DATA, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.HUMAN_NEXT_NODE, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.AWAITING_HUMAN_FEEDBACK, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.PLAN_STEPS, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.CURRENT_PLAN_STEP_INDEX, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.PLANNER_ENABLED, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.PLAN_FINISHED, KeyStrategy.REPLACE);
			strategies.put(SearchLiteGraphStateKeys.PLAN_FINISHED_REASON, KeyStrategy.REPLACE);
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
			.addNode(FEASIBILITY_NODE, node_async(feasibilityNode))
			.addNode(PLANNER_NODE, node_async(plannerNode))
			.addNode(PLAN_EXECUTOR_NODE, node_async(planExecutorNode))
			.addNode(HUMAN_FEEDBACK_NODE, node_async(humanFeedbackNode))
			.addNode(SQL_GENERATE_NODE, node_async(sqlGenerateNode))
			.addNode(SQL_CONSISTENCY_NODE, node_async(sqlConsistencyNode))
			.addNode(SQL_EXECUTE_NODE, node_async(sqlExecuteNode))
			.addNode(SQL_REPAIR_NODE, node_async(sqlRepairNode))
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
			.addEdge(ENHANCE_NODE, FEASIBILITY_NODE)
			.addConditionalEdges(FEASIBILITY_NODE, edge_async(feasibilityDispatcher),
					Map.of(PLANNER_NODE, PLANNER_NODE, PREPARE_RESULT_NODE, PREPARE_RESULT_NODE))
			.addEdge(PLANNER_NODE, PLAN_EXECUTOR_NODE)
			.addConditionalEdges(PLAN_EXECUTOR_NODE, edge_async(planExecutorDispatcher),
					Map.of(SQL_GENERATE_NODE, SQL_GENERATE_NODE, PREPARE_RESULT_NODE, PREPARE_RESULT_NODE,
							HUMAN_FEEDBACK_NODE, HUMAN_FEEDBACK_NODE))
			.addConditionalEdges(HUMAN_FEEDBACK_NODE, edge_async(humanFeedbackDispatcher),
					Map.of(PLAN_EXECUTOR_NODE, PLAN_EXECUTOR_NODE, SQL_GENERATE_NODE, SQL_GENERATE_NODE,
							PLANNER_NODE, PLANNER_NODE,
							PREPARE_RESULT_NODE, PREPARE_RESULT_NODE, END, END))
			.addConditionalEdges(SQL_GENERATE_NODE, edge_async(sqlGenerateDispatcher),
					Map.of(SQL_CONSISTENCY_NODE, SQL_CONSISTENCY_NODE, PREPARE_RESULT_NODE, PREPARE_RESULT_NODE))
			.addConditionalEdges(SQL_CONSISTENCY_NODE, edge_async(sqlConsistencyDispatcher),
					Map.of(SQL_EXECUTE_NODE, SQL_EXECUTE_NODE, PREPARE_RESULT_NODE, PREPARE_RESULT_NODE))
			.addConditionalEdges(SQL_EXECUTE_NODE, edge_async(sqlExecuteDispatcher),
					Map.of(PREPARE_RESULT_NODE, PREPARE_RESULT_NODE, SQL_REPAIR_NODE, SQL_REPAIR_NODE,
							PLAN_EXECUTOR_NODE, PLAN_EXECUTOR_NODE))
			.addConditionalEdges(SQL_REPAIR_NODE, edge_async(sqlRepairDispatcher),
					Map.of(PLAN_EXECUTOR_NODE, PLAN_EXECUTOR_NODE, SQL_RETRY_NODE, SQL_RETRY_NODE))
			.addEdge(SQL_RETRY_NODE, SQL_GENERATE_NODE)
			.addConditionalEdges(PREPARE_RESULT_NODE, edge_async(resultModeDispatcher),
					Map.of(RESULT_NODE, RESULT_NODE))
			.addEdge(RESULT_NODE, END);
		return graph;
	}

	@Bean(destroyMethod = "shutdown")
	public ExecutorService searchLiteGraphExecutor(
			@Value("${search.lite.graph.executor.threads:12}") int threadCount) {
		int poolSize = Math.max(1, threadCount);
		return Executors.newFixedThreadPool(poolSize, runnable -> {
			Thread thread = new Thread(runnable);
			thread.setName("search-lite-graph-" + thread.getId());
			thread.setDaemon(true);
			return thread;
		});
	}

}
