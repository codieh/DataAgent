package com.alibaba.cloud.ai.dataagentbackend.lite.step;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;

/**
 * {@code search-lite} 流水线中的一个阶段（Step）。
 * <p>
 * 约定：
 * <ul>
 *   <li>{@link SearchLiteStepResult#messages()}：该阶段要流式输出给前端的消息（SSE）。</li>
 *   <li>{@link SearchLiteStepResult#updatedState()}：该阶段处理后的状态，会传递给下一个 Step。</li>
 * </ul>
 * Step 的执行顺序由 {@code @Order} 决定，并由 {@code SearchLiteOrchestrator} 串联执行。
 */
public interface SearchLiteStep {

	SearchLiteStage stage();

	SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state);

}

