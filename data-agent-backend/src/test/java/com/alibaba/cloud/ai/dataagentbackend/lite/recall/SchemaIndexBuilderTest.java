package com.alibaba.cloud.ai.dataagentbackend.lite.recall;

import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaColumn;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaForeignKey;
import com.alibaba.cloud.ai.dataagentbackend.api.lite.SchemaTable;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SchemaIndexBuilderTest {

	private final SchemaIndexBuilder builder = new SchemaIndexBuilder();

	@Test
	void should_build_table_and_column_documents() {
		SchemaTable orders = new SchemaTable("orders", "订单表",
				List.of(new SchemaColumn("id", "int", "int", true, true, "订单ID"),
						new SchemaColumn("user_id", "int", "int", true, false, "用户ID"),
						new SchemaColumn("total_amount", "decimal", "decimal(10,2)", true, false, "订单总金额")),
				List.of(new SchemaForeignKey("user_id", "users", "id")));

		SchemaIndex index = builder.build(List.of(orders));

		assertEquals(1, index.tableDocuments().size());
		assertEquals(3, index.columnDocuments().size());
		assertTrue(index.tableDocuments().get(0).content().contains("外键关系"));
		assertTrue(index.columnDocuments().get(2).title().contains("orders.total_amount"));
		assertEquals("orders", index.columnDocuments().get(0).metadata().get("tableName"));
	}

}
