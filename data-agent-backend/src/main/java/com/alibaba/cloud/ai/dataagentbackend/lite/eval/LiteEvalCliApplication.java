package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import com.alibaba.cloud.ai.dataagentbackend.DataAgentBackendApplication;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

public final class LiteEvalCliApplication {

	private static final Logger log = LoggerFactory.getLogger(LiteEvalCliApplication.class);

	static final String SUITE_PROPERTY = "--search.lite.eval.suite=";

	private LiteEvalCliApplication() {
	}

	public static void main(String[] args) throws Exception {
		if (containsHelpFlag(args)) {
			log.info("usage: java ... LiteEvalCliApplication [--suite=quick|standard|all] [spring args]");
			return;
		}
		String[] applicationArgs = mergeSuiteArgument(args);
		ConfigurableApplicationContext context = new SpringApplicationBuilder(DataAgentBackendApplication.class)
			.web(WebApplicationType.NONE)
			.run(applicationArgs);
		int exitCode = 0;
		try {
			EvalRunReport report = context.getBean(EvalRunner.class).runDefaultSuite();
			log.info("lite eval finished: suite={}, totalCases={}, passedCases={}, failedCases={}", report.suite(),
					report.totalCases(), report.passedCases(), report.failedCases());
		}
		catch (Exception ex) {
			exitCode = 1;
			log.error("lite eval failed", ex);
			throw ex;
		}
		finally {
			int finalExitCode = exitCode;
			System.exit(org.springframework.boot.SpringApplication.exit(context, () -> finalExitCode));
		}
	}

	static String[] mergeSuiteArgument(String[] args) {
		String suite = null;
		java.util.List<String> forwarded = new java.util.ArrayList<>();
		for (String arg : args) {
			if (arg != null && arg.startsWith("--suite=")) {
				suite = arg.substring("--suite=".length()).trim();
				continue;
			}
			forwarded.add(arg);
		}
		if (suite == null || suite.isBlank()) {
			return forwarded.toArray(String[]::new);
		}
		forwarded.add(SUITE_PROPERTY + suite);
		return forwarded.toArray(String[]::new);
	}

	private static boolean containsHelpFlag(String[] args) {
		for (String arg : args) {
			if ("--help".equalsIgnoreCase(arg) || "-h".equalsIgnoreCase(arg)) {
				return true;
			}
		}
		return false;
	}

}
