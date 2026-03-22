package com.alibaba.cloud.ai.dataagentbackend.lite;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;

import java.time.Instant;

public final class SearchLiteMessages {

	private SearchLiteMessages() {
	}

	public static SearchLiteMessage message(SearchLiteContext ctx, SearchLiteStage stage, SearchLiteMessageType type,
			String chunk, Object payload) {
		return new SearchLiteMessage(ctx.threadId(), stage, type, chunk, payload, false, null, ctx.nextSeq(),
				Instant.now());
	}

	public static SearchLiteMessage done(SearchLiteContext ctx, SearchLiteStage stage, SearchLiteMessageType type,
			String chunk, Object payload) {
		return new SearchLiteMessage(ctx.threadId(), stage, type, chunk, payload, true, null, ctx.nextSeq(),
				Instant.now());
	}

	public static SearchLiteMessage error(SearchLiteContext ctx, SearchLiteStage stage, String errorMessage) {
		return new SearchLiteMessage(ctx.threadId(), stage, SearchLiteMessageType.TEXT, null, null, true, errorMessage,
				ctx.nextSeq(), Instant.now());
	}

}

