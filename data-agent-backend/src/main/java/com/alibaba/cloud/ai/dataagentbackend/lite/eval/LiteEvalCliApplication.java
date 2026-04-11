package com.alibaba.cloud.ai.dataagentbackend.lite.eval;

import com.alibaba.cloud.ai.dataagentbackend.DataAgentBackendApplication;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;

public final class LiteEvalCliApplication {

	private static final Logger log = LoggerFactory.getLogger(LiteEvalCliApplication.class);

	private LiteEvalCliApplication() {
	}

	public static void main(String[] args) throws Exception {
		ConfigurableApplicationContext context = new SpringApplicationBuilder(DataAgentBackendApplication.class)
			.web(WebApplicationType.NONE)
			.run(args);
		int exitCode = 0;
		try {
			EvalRunReport report = context.getBean(EvalRunner.class).runDefaultSuite();
			log.info("lite eval finished: totalCases={}, passedCases={}, failedCases={}", report.totalCases(),
					report.passedCases(), report.failedCases());
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

}
