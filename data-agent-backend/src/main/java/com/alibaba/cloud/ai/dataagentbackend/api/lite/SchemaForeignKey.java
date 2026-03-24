package com.alibaba.cloud.ai.dataagentbackend.api.lite;

/**
 * 外键关系（精简版）。
 */
public record SchemaForeignKey(String columnName, String refTableName, String refColumnName) {
}

