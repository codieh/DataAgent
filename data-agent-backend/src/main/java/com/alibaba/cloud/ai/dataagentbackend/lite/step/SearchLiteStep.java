package com.alibaba.cloud.ai.dataagentbackend.lite.step;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;

public interface SearchLiteStep {

	SearchLiteStage stage();

	SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state);

}

