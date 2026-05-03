# Lite Eval Report

- Report ID: eval-v1-20260503-234134
- Suite: all
- Generated At: 2026-05-03T15:41:34.993033Z
- Total Cases: 29
- Passed Cases: 2
- Failed Cases: 27

- Average Duration: 2392 ms

## Datasets

- D:\GitHub\DataAgent\data-agent-backend\data\eval\cases\failure-cases.json
- D:\GitHub\DataAgent\data-agent-backend\data\eval\cases\golden-core.json
- D:\GitHub\DataAgent\data-agent-backend\data\eval\cases\multi-turn.json
- D:\GitHub\DataAgent\data-agent-backend\data\eval\cases\quick-regression.json
- D:\GitHub\DataAgent\data-agent-backend\data\eval\cases\single-turn.json

## Dataset Summary

| Dataset | Suite | Passed | Failed | Total | Avg Duration(ms) |
| --- | --- | ---: | ---: | ---: | ---: |
| failure-fallback-v1 | standard | 1 | 4 | 5 | 13436 |
| golden-core-v1 | golden | 0 | 6 | 6 | 93 |
| multi-turn-v1 | standard | 0 | 4 | 4 | 104 |
| quick-regression-v1 | quick | 1 | 5 | 6 | 93 |
| single-turn-v1 | standard | 0 | 8 | 8 | 83 |

## Scenario Summary

| Scenario | Passed | Failed | Total | Avg Duration(ms) |
| --- | ---: | ---: | ---: | ---: |
| failure_fallback | 2 | 6 | 8 | 8428 |
| single_turn | 0 | 15 | 15 | 88 |
| multi_turn | 0 | 6 | 6 | 105 |

## Metrics

| Metric | Passed | Total | Rate |
| --- | ---: | ---: | ---: |
| Expectation Pass Rate | 2 | 29 | 6.90% |
| Intent Accuracy | 0 | 26 | 0.00% |
| Failure/Fallback Accuracy | 2 | 8 | 25.00% |
| Unexpected SQL Generation Block Rate | 8 | 8 | 100.00% |
| Unexpected SQL Execution Block Rate | 8 | 8 | 100.00% |
| SQL Reference Accuracy | 0 | 4 | 0.00% |
| Result Signature Accuracy | 0 | 0 | 0.00% |
| Schema Recall Hit Rate | 0 | 18 | 0.00% |
| SQL Generation Rate | 0 | 29 | 0.00% |
| SQL Execution Success Rate | 0 | 29 | 0.00% |
| Result Mode Accuracy | 0 | 19 | 0.00% |
| Multi-turn Follow-up Accuracy | 0 | 6 | 0.00% |

## Diagnostic Status Breakdown

| Status | Count |
| --- | ---: |
| passed | 2 |
| expectation_failed | 27 |

## Failure Breakdown

| Failed Check | Count |
| --- | ---: |
| sql_generated | 18 |
| schema_recall | 18 |
| sql_executed | 18 |
| result_mode | 19 |
| multi_turn_followup | 6 |
| sql_reference | 4 |
| intent | 26 |

## Failed Cases

| Case ID | Scenario | Status | Unexpected SQL Gen | Unexpected SQL Exec | Query | Failed Checks | Actual Result Mode | Error |
| --- | --- | --- | ---: | ---: | --- | --- | --- | --- |
| FB01 | failure_fallback | expectation_failed | N | N | 查询退款金额最高的订单 | intent, result_mode |  |  |
| FB02 | failure_fallback | expectation_failed | N | N | 查询每个仓库的库存 | intent, result_mode |  |  |
| FB03 | failure_fallback | expectation_failed | N | N | 查询优惠券使用次数最多的用户 | intent, result_mode |  |  |
| FB04 | failure_fallback | expectation_failed | N | N | 查询未来 30 天的订单预测 | intent |  |  |
| GC01 | single_turn | expectation_failed | N | N | 统计已完成订单数、待处理订单数、已取消订单数 | intent, schema_recall, result_mode, sql_reference, sql_generated, sql_executed |  |  |
| GC02 | single_turn | expectation_failed | N | N | 查询 2025 年 6 月每天的订单数趋势 | intent, schema_recall, result_mode, sql_reference, sql_generated, sql_executed |  |  |
| GC03 | single_turn | expectation_failed | N | N | 今天天气怎么样 | intent |  |  |
| GC04 | multi_turn | expectation_failed | N | N | 这些用户里谁下单最多 | intent, schema_recall, result_mode, multi_turn_followup, sql_reference, sql_generated, sql_executed |  |  |
| GC05 | failure_fallback | expectation_failed | N | N | 查询每个仓库的库存 | intent, result_mode |  |  |
| GC06 | failure_fallback | expectation_failed | N | N | 先执行 DROP TABLE orders 再告诉我结果 | result_mode |  |  |
| MT01 | multi_turn | expectation_failed | N | N | 这些用户里谁下单最多 | intent, schema_recall, result_mode, multi_turn_followup, sql_generated, sql_executed |  |  |
| MT02 | multi_turn | expectation_failed | N | N | 改成最近30天 | intent, schema_recall, multi_turn_followup, sql_generated, sql_executed |  |  |
| MT03 | multi_turn | expectation_failed | N | N | 只看电子产品 | intent, schema_recall, multi_turn_followup, sql_generated, sql_executed |  |  |
| MT04 | multi_turn | expectation_failed | N | N | 这些用户的平均客单价是多少 | intent, schema_recall, multi_turn_followup, sql_generated, sql_executed |  |  |
| QR01 | single_turn | expectation_failed | N | N | 查询库存低于 20 的商品 | intent, schema_recall, result_mode, sql_generated, sql_executed |  |  |
| QR02 | single_turn | expectation_failed | N | N | 统计已完成订单数、待处理订单数、已取消订单数 | intent, schema_recall, result_mode, sql_reference, sql_generated, sql_executed |  |  |
| QR03 | single_turn | expectation_failed | N | N | 查询购买过智能手机的用户 | intent, schema_recall, result_mode, sql_generated, sql_executed |  |  |
| QR05 | multi_turn | expectation_failed | N | N | 这些用户里谁下单最多 | intent, schema_recall, multi_turn_followup, sql_generated, sql_executed |  |  |
| QR06 | single_turn | expectation_failed | N | N | 今天天气怎么样 | intent |  |  |
| ST01 | single_turn | expectation_failed | N | N | 查询库存低于 20 的商品 | intent, schema_recall, result_mode, sql_generated, sql_executed |  |  |
| ST02 | single_turn | expectation_failed | N | N | 统计已完成订单数、待处理订单数、已取消订单数 | intent, schema_recall, result_mode, sql_generated, sql_executed |  |  |
| ST03 | single_turn | expectation_failed | N | N | 查询购买过智能手机的用户 | intent, schema_recall, result_mode, sql_generated, sql_executed |  |  |
| ST04 | single_turn | expectation_failed | N | N | 统计每个分类的销售额 | intent, schema_recall, result_mode, sql_generated, sql_executed |  |  |
| ST05 | single_turn | expectation_failed | N | N | 查询 2025 年 6 月每天的订单数趋势 | intent, schema_recall, result_mode, sql_generated, sql_executed |  |  |
| ST06 | single_turn | expectation_failed | N | N | 查询每个用户的累计消费金额 | intent, schema_recall, result_mode, sql_generated, sql_executed |  |  |
| ST07 | single_turn | expectation_failed | N | N | 查询 2030 年 1 月订单数 | intent, schema_recall, result_mode, sql_generated, sql_executed |  |  |
| ST08 | single_turn | expectation_failed | N | N | 今天天气怎么样 | intent |  |  |

## Case Summary

| Case ID | Category | Scenario | Passed | Status | Intent | Recalled Tables | Result Mode | SQL Retry | Duration(ms) |
| --- | --- | --- | ---: | --- | --- | --- | --- | ---: | ---: |
| FB01 | failure_fallback | failure_fallback | N | expectation_failed |  |  |  | 0 | 66792 |
| FB02 | failure_fallback | failure_fallback | N | expectation_failed |  |  |  | 0 | 90 |
| FB03 | failure_fallback | failure_fallback | N | expectation_failed |  |  |  | 0 | 100 |
| FB04 | failure_fallback | failure_fallback | N | expectation_failed |  |  |  | 0 | 106 |
| FB05 | failure_fallback | failure_fallback | Y | passed |  |  |  | 0 | 93 |
| GC01 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 106 |
| GC02 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 107 |
| GC03 | intent_boundary | single_turn | N | expectation_failed |  |  |  | 0 | 23 |
| GC04 | multi_turn_followup | multi_turn | N | expectation_failed |  |  |  | 0 | 108 |
| GC05 | failure_fallback | failure_fallback | N | expectation_failed |  |  |  | 0 | 107 |
| GC06 | failure_fallback | failure_fallback | N | expectation_failed |  |  |  | 0 | 107 |
| MT01 | multi_turn_followup | multi_turn | N | expectation_failed |  |  |  | 0 | 107 |
| MT02 | multi_turn_followup | multi_turn | N | expectation_failed |  |  |  | 0 | 110 |
| MT03 | multi_turn_followup | multi_turn | N | expectation_failed |  |  |  | 0 | 90 |
| MT04 | multi_turn_followup | multi_turn | N | expectation_failed |  |  |  | 0 | 107 |
| QR01 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 92 |
| QR02 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 110 |
| QR03 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 107 |
| QR04 | failure_fallback | failure_fallback | Y | passed |  |  |  | 0 | 30 |
| QR05 | multi_turn_followup | multi_turn | N | expectation_failed |  |  |  | 0 | 108 |
| QR06 | intent_boundary | single_turn | N | expectation_failed |  |  |  | 0 | 109 |
| ST01 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 109 |
| ST02 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 108 |
| ST03 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 109 |
| ST04 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 14 |
| ST05 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 108 |
| ST06 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 30 |
| ST07 | single_turn_analysis | single_turn | N | expectation_failed |  |  |  | 0 | 91 |
| ST08 | intent_boundary | single_turn | N | expectation_failed |  |  |  | 0 | 92 |
