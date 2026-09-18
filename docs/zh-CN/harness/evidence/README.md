# 本轮测试证据

这里保存实际执行日志，文件路径统一脱敏为 `<repo>`。Red 日志反映占位实现的已执行失败，Green 日志反映实现后的实际通过；不会把无密钥的工具联调记录为模型调用。

- workbench-red.txt：18 项失败。
- http-red.txt：8 项失败。
- python-green.txt：66 项通过。
- plugin-green.txt：15 项通过。
- harness-integration-green.txt：11 工具到实际业务服务的联调通过。
- harness-web.txt：官方运行时实际加载摘要，登录令牌不记录。
