package com.alibaba.cloud.ai.dataagentbackend.api.lite;

import java.util.List;

/**
 * 数据库表的元信息（精简版）。
 */
public record SchemaTable(String name, String comment, List<SchemaColumn> columns, List<SchemaForeignKey> foreignKeys) {
}

