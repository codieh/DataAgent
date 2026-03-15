/*
 * Copyright 2024-2026 the original author or authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package com.alibaba.cloud.ai.dataagent.controller;

import com.alibaba.cloud.ai.dataagent.dto.ModelConfigDTO;
import com.alibaba.cloud.ai.dataagent.enums.ModelType;
import com.alibaba.cloud.ai.dataagent.service.aimodelconfig.ModelConfigDataService;
import com.alibaba.cloud.ai.dataagent.service.aimodelconfig.ModelConfigOpsService;
import com.alibaba.cloud.ai.dataagent.vo.ApiResponse;
import com.alibaba.cloud.ai.dataagent.vo.ModelCheckVo;
import jakarta.validation.Valid;
import lombok.AllArgsConstructor;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.List;

@AllArgsConstructor
@RestController
@RequestMapping("/api/model-config")
public class ModelConfigController {

	private final ModelConfigDataService modelConfigDataService;

	private final ModelConfigOpsService modelConfigOpsService;

	@GetMapping("/list")
	public ApiResponse<List<ModelConfigDTO>> list() {
		try {
			return ApiResponse.success("OK", modelConfigDataService.listConfigs());
		}
		catch (Exception e) {
			return ApiResponse.error("Failed to list configs: " + e.getMessage());
		}
	}

	@PostMapping("/add")
	public ApiResponse<String> add(@Valid @RequestBody ModelConfigDTO config) {
		try {
			modelConfigDataService.addConfig(config);
			return ApiResponse.success("Saved");
		}
		catch (Exception e) {
			return ApiResponse.error("Save failed: " + e.getMessage());
		}
	}

	@PutMapping("/update")
	public ApiResponse<String> update(@Valid @RequestBody ModelConfigDTO config) {
		try {
			modelConfigOpsService.updateAndRefresh(config);
			return ApiResponse.success("Updated");
		}
		catch (Exception e) {
			return ApiResponse.error("Update failed: " + e.getMessage());
		}
	}

	@DeleteMapping("/{id}")
	public ApiResponse<String> delete(@PathVariable Integer id) {
		try {
			modelConfigDataService.deleteConfig(id);
			return ApiResponse.success("Deleted");
		}
		catch (Exception e) {
			return ApiResponse.error("Delete failed: " + e.getMessage());
		}
	}

	@PostMapping("/activate/{id}")
	public ApiResponse<String> activate(@PathVariable Integer id) {
		try {
			modelConfigOpsService.activateConfig(id);
			return ApiResponse.success("Activated");
		}
		catch (Exception e) {
			return ApiResponse.error("Activate failed: " + e.getMessage());
		}
	}

	@PostMapping("/test")
	public Mono<ApiResponse<String>> testConnection(@Valid @RequestBody ModelConfigDTO config) {
		return Mono.<ApiResponse<String>>fromCallable(() -> {
				modelConfigOpsService.testConnection(config);
				return ApiResponse.success("Connection test succeeded.");
			})
			.subscribeOn(Schedulers.boundedElastic())
			.onErrorResume(e -> Mono.just(ApiResponse.<String>error("Connection test failed: " + e.getMessage())));
	}

	@GetMapping("/check-ready")
	public ApiResponse<ModelCheckVo> checkReady() {
		ModelConfigDTO chatModel = modelConfigDataService.getActiveConfigByType(ModelType.CHAT);
		ModelConfigDTO embeddingModel = modelConfigDataService.getActiveConfigByType(ModelType.EMBEDDING);

		boolean chatModelReady = chatModel != null;
		boolean embeddingModelReady = embeddingModel != null;
		boolean ready = chatModelReady && embeddingModelReady;

		return ApiResponse.success("OK", ModelCheckVo.builder()
			.chatModelReady(chatModelReady)
			.embeddingModelReady(embeddingModelReady)
			.ready(ready)
			.build());
	}

}

