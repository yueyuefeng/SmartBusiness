# Harness 插件 TDD 记录

核查日期：2026-09-18。原生 Windows，Node v24.21.0。

## Red：先写验收测试

先编写 `tests/plugin.test.mjs`，再添加只抛出 `TDD: client not implemented` 的占位接口。使用真正的 `@deepseek-ai/dsh-tools@0.1.6-alpha.2` ToolRuntime 和本机临时 HTTP 服务，不使用伪造 Harness 注册器。

命令：`npm test`。首次实际运行退出码 1，测试 12 条，成功 1，失败 11。成功项是拒绝非法 API 配置的断言；由于占位接口始终抛错，这一项在 Red 阶段不构成功能证据。其余失败均为 `TDD: client not implemented`。

脱敏失败摘要：

```text
tests 12
pass 1
fail 11
exit 1
Error: TDD: client not implemented
```

## Green：实现后验证

实现工具映射、参数约束、HTTP 认证和取消后，曾因测试清理错误调用 `ctx.dispose()` 失败；查阅真实 Cordis 类型后改为 `ctx.fiber.dispose()`。这是测试装置修正，没有删除业务断言。

第二个 Red：新增工具执行边界回归用例后，15 条中 13 条成功，2 条失败；真实 Harness 管线原先允许测试 shell 工具和伪造 `sb_` 前缀工具执行。随后加入官方 `ctx.tools.guard()` 精确白名单，使用返回拒绝理由的最终单调拒绝，覆盖普通 policy 试图放行的情况。

```text
Second Red: tests 15, pass 13, fail 2, exit 1
shell denial: false !== true
spoofed sb_ tool denial: false !== true
```

最终 Green：2026-09-18，`npm test` 实际退出码 0，15 条全部通过。主流程复跑确认。测试只使用测试专用 token，不调用付费模型或外部社交平台。

随后运行 `python scripts/check_harness_integration.py`（仓库根目录），连接临时数据库上的真实 Python 服务。首次因测试探针的 schema 未显式设置 additionalProperties 失败，按官方 schema 合同补齐后，11 个工具均通过联调，审计事件 9 条；重放没有多记事件，shell 与 Agent 评审被拒绝。

官方 Web 也已加载插件并输出注册成功消息。以上验证没有模型推理；真实模型选择工具、回答质量与费用需要配置密钥后另行评估。
