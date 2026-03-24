package com.alibaba.cloud.ai.dataagentbackend.api.lite;

/**
 * 数据库列的元信息（精简版）。
 */
public record SchemaColumn(String name, String dataType, String columnType, boolean notNull, boolean primaryKey,
		String comment) {
}

