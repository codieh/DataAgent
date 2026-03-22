package com.alibaba.cloud.ai.dataagentbackend.llm.anthropic;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import com.fasterxml.jackson.databind.ObjectMapper;

@Configuration
@EnableConfigurationProperties(AnthropicProperties.class)
public class AnthropicConfiguration {

	@Bean
	public AnthropicClient anthropicClient(WebClient.Builder builder, AnthropicProperties properties,
			ObjectMapper objectMapper) {
		return new AnthropicClient(builder, properties, objectMapper);
	}

}
