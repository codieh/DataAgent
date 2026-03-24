package com.alibaba.cloud.ai.dataagentbackend.lite.step.impl;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaColumn;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaForeignKey;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteMessageType;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteStage;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SearchLiteState;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteContext;
import com.alibaba.cloud.ai.dataagentbackend.lite.SearchLiteMessages;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStep;
import com.alibaba.cloud.ai.dataagentbackend.lite.step.SearchLiteStepResult;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * Schema mock：用于稳定回归测试与离线演示（不依赖真实数据库）。
 */
@Component
@Order(30)
@ConditionalOnProperty(name = "search.lite.schema.introspect.provider", havingValue = "mock")
public class SchemaMockStep implements SearchLiteStep {

	@Override
	public SearchLiteStage stage() {
		return SearchLiteStage.SCHEMA;
	}

	@Override
	public SearchLiteStepResult run(SearchLiteContext context, SearchLiteState state) {
		List<SchemaTable> tables = demoTables();
		state.setSchemaTableDetails(tables);
		state.setSchemaTables(tables.stream().map(SchemaTable::name).toList());
		state.setSchemaText("(mock schema)\nTABLE orders(id,user_id,order_date,total_amount,status)\nTABLE users(id,username,email,created_at)");

		Flux<SearchLiteMessage> messages = Flux
			.just(SearchLiteMessages.message(context, stage(), SearchLiteMessageType.TEXT, "正在加载数据库结构（schema）...", null),
					SearchLiteMessages.message(context, stage(), SearchLiteMessageType.JSON, null,
							Map.of("tables", state.getSchemaTables(), "mock", true)))
			.delayElements(Duration.ofMillis(30));

		return new SearchLiteStepResult(messages, Mono.just(state));
	}

	private static List<SchemaTable> demoTables() {
		SchemaTable users = new SchemaTable("users", "用户表",
				List.of(new SchemaColumn("id", "int", "int", true, true, "用户ID"),
						new SchemaColumn("username", "varchar", "varchar(50)", true, false, "用户名"),
						new SchemaColumn("email", "varchar", "varchar(100)", true, false, "邮箱"),
						new SchemaColumn("created_at", "datetime", "datetime", false, false, "注册时间")),
				List.of());

		SchemaTable orders = new SchemaTable("orders", "订单表",
				List.of(new SchemaColumn("id", "int", "int", true, true, "订单ID"),
						new SchemaColumn("user_id", "int", "int", true, false, "下单用户ID"),
						new SchemaColumn("order_date", "datetime", "datetime", false, false, "下单时间"),
						new SchemaColumn("total_amount", "decimal", "decimal(10,2)", true, false, "订单总金额"),
						new SchemaColumn("status", "varchar", "varchar(20)", false, false, "状态")),
				List.of(new SchemaForeignKey("user_id", "users", "id")));

		return List.of(users, orders);
	}

}

