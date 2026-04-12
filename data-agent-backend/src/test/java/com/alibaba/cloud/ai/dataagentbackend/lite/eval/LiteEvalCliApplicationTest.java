package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;

class LiteEvalCliApplicationTest {

	@Test
	void mergeSuiteArgument_should_forward_spring_property_for_short_flag() {
		String[] merged = LiteEvalCliApplication.mergeSuiteArgument(new String[] { "--suite=quick", "--debug=true" });
		assertArrayEquals(new String[] { "--debug=true", "--search.lite.eval.suite=quick" }, merged);
	}

	@Test
	void mergeSuiteArgument_should_leave_args_unchanged_when_suite_not_present() {
		String[] merged = LiteEvalCliApplication.mergeSuiteArgument(new String[] { "--debug=true" });
		assertArrayEquals(new String[] { "--debug=true" }, merged);
	}

}
