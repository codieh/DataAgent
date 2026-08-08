package com.alibaba.cloud.ai.dataagentbackend.api.lite;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class SearchLitePlanStep {

	private int step;

	private String instruction;

	private String tool = "SQL";

	private String status = "PENDING";

	private String sql;

	private int rowCount;

	private List<Map<String, Object>> previewRows = new ArrayList<>();

	private String error;

	private String summarySnippet;

	public SearchLitePlanStep() {
	}

	public SearchLitePlanStep(int step, String instruction) {
		this.step = step;
		this.instruction = instruction;
	}

	public int getStep() {
		return step;
	}

	public void setStep(int step) {
		this.step = step;
	}

	public String getInstruction() {
		return instruction;
	}

	public void setInstruction(String instruction) {
		this.instruction = instruction;
	}

	public String getTool() {
		return tool;
	}

	public void setTool(String tool) {
		this.tool = tool;
	}

	public String getStatus() {
		return status;
	}

	public void setStatus(String status) {
		this.status = status;
	}

	public String getSql() {
		return sql;
	}

	public void setSql(String sql) {
		this.sql = sql;
	}

	public int getRowCount() {
		return rowCount;
	}

	public void setRowCount(int rowCount) {
		this.rowCount = Math.max(0, rowCount);
	}

	public List<Map<String, Object>> getPreviewRows() {
		return previewRows;
	}

	public void setPreviewRows(List<Map<String, Object>> previewRows) {
		this.previewRows = sanitizeRows(previewRows);
	}

	public String getError() {
		return error;
	}

	public void setError(String error) {
		this.error = error;
	}

	public String getSummarySnippet() {
		return summarySnippet;
	}

	public void setSummarySnippet(String summarySnippet) {
		this.summarySnippet = summarySnippet;
	}

	private List<Map<String, Object>> sanitizeRows(List<Map<String, Object>> rows) {
		if (rows == null) {
			return new ArrayList<>();
		}
		List<Map<String, Object>> sanitized = new ArrayList<>(rows.size());
		for (Map<String, Object> row : rows) {
			sanitized.add(sanitizeMap(row));
		}
		return sanitized;
	}

	private Map<String, Object> sanitizeMap(Map<String, Object> raw) {
		Map<String, Object> sanitized = new java.util.LinkedHashMap<>();
		if (raw == null) {
			return sanitized;
		}
		for (Map.Entry<String, Object> entry : raw.entrySet()) {
			String key = entry.getKey();
			if ("@class".equals(key)) {
				continue;
			}
			sanitized.put(key, sanitizeValue(entry.getValue()));
		}
		return sanitized;
	}

	private Object sanitizeValue(Object value) {
		if (value instanceof Map<?, ?> map) {
			Map<String, Object> nested = new java.util.LinkedHashMap<>();
			for (Map.Entry<?, ?> entry : map.entrySet()) {
				String key = String.valueOf(entry.getKey());
				if ("@class".equals(key)) {
					continue;
				}
				nested.put(key, sanitizeValue(entry.getValue()));
			}
			return nested;
		}
		if (value instanceof List<?> list) {
			List<Object> nested = new ArrayList<>(list.size());
			for (Object item : list) {
				nested.add(sanitizeValue(item));
			}
			return nested;
		}
		return value;
	}

}
