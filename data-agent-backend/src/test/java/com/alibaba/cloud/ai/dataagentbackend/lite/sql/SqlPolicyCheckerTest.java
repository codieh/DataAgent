package com.alibaba.cloud.ai.dataagentbackend.lite.sql;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SqlPolicyCheckerTest {

	private final SqlPolicyChecker checker = new SqlPolicyChecker(
			"phone,mobile,email,id_card,idcard,salary,wage,address,bank_card");

	@Test
	void should_block_sensitive_field_query() {
		SqlPolicyChecker.PolicyDecision decision = checker.inspect("SELECT user_id, email FROM users LIMIT 20");

		assertTrue(decision.blocked());
		assertEquals("blocked_sensitive_sql", decision.resultMode());
	}

	@Test
	void should_block_select_all_export_without_limit() {
		SqlPolicyChecker.PolicyDecision decision = checker.inspect("SELECT * FROM orders");

		assertTrue(decision.blocked());
		assertEquals("blocked_wide_export", decision.resultMode());
	}

	@Test
	void should_allow_aggregated_query_without_limit() {
		SqlPolicyChecker.PolicyDecision decision = checker.inspect(
				"SELECT user_id, SUM(total_amount) AS total_spent FROM orders GROUP BY user_id");

		assertFalse(decision.blocked());
	}

}
