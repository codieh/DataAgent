package com.alibaba.cloud.ai.dataagentbackend.api.lite;

public enum SearchLiteStage {
	INTENT,
	EVIDENCE,
	SCHEMA,
	SCHEMA_RECALL,
	ENHANCE,
	PLANNER,
	PLAN_EXECUTOR,
	HUMAN_FEEDBACK,
	SQL_GENERATE,
	SQL_EXECUTE,
	RESULT
}
