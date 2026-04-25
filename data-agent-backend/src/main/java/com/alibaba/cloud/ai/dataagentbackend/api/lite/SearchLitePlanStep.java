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
		this.previewRows = previewRows == null ? new ArrayList<>() : previewRows;
	}

	public String getError() {
		return error;
	}

	public void setError(String error) {
		this.error = error;
	}

}
