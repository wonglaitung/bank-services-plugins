# 文档阅读指南 (docs/README.md)

本文件为 docs 目录的快速导览与推荐阅读顺序，帮助新人或维护者快速上手并定位关键文档。

## 建议的阅读顺序（按优先级，从高到低）

1. mvp_finance_digital_twin.md
   - 链接: https://github.com/wonglaitung/bank-services-plugins/blob/ce54c8e0595b76c8bc9134d8240d6c810c0f6581/docs/mvp_finance_digital_twin.md
   - 说明：项目/产品概览，包含目标、用例与背景。先读以建立整体语境。
   - 估时：15–25 分钟

2. mcp_prototype_sidecar.md
   - 链接: https://github.com/wonglaitung/bank-services-plugins/blob/ce54c8e0595b76c8bc9134d8240d6c810c0f6581/docs/mcp_prototype_sidecar.md
   - 说明：架构与运行时设计，描述 sidecar 原型、组件交互与部署要点。
   - 估时：20–30 分钟

3. backend_api_spec.md
   - 链接: https://github.com/wonglaitung/bank-services-plugins/blob/ce54c8e0595b76c8bc9134d8240d6c810c0f6581/docs/backend_api_spec.md
   - 说明：后端 API 规范（端点、请求/响应、数据契约），实现与集成参考。
   - 估时：10–20 分钟

4. programmer_skill.md
   - 链接: https://github.com/wonglaitung/bank-services-plugins/blob/ce54c8e0595b76c8bc9134d8240d6c810c0f6581/docs/programmer_skill.md
   - 说明：开发者惯例、编码/测试约定及上手提示。
   - 估时：10–15 分钟

5. mcp_tool_description_best_practices.md
   - 链接: https://github.com/wonglaitung/bank-services-plugins/blob/ce54c8e0595b76c8bc9134d8240d6c810c0f6581/docs/mcp_tool_description_best_practices.md
   - 说明：工具/插件描述与设计最佳实践，适合新增或改进工具时阅读。
   - 估时：15–20 分钟

6. mcp_security_authentication.md
   - 链接: https://github.com/wonglaitung/bank-services-plugins/blob/ce54c8e0595b76c8bc9134d8240d6c810c0f6581/docs/mcp_security_authentication.md
   - 说明：详尽的认证与安全策略，包含 threat model、token 流程等，部署/审核前必读。
   - 估时：30–45 分钟

7. mcp_local_credential_encryption.md
   - 链接: https://github.com/wonglaitung/bank-services-plugins/blob/ce54c8e0595b76c8bc9134d8240d6c810c0f6581/docs/mcp_local_credential_encryption.md
   - 说明：本地凭证加密实现细节与注意点，关注存储/加密流程与依赖。
   - 估时：10–15 分钟

8. mcp_security.html
   - 链接: https://github.com/wonglaitung/bank-services-plugins/blob/ce54c8e0595b76c8bc9134d8240d6c810c0f6581/docs/mcp_security.html
   - 说明：安全说明的 HTML 渲染版本或旧版，作为补充或交叉核对。
   - 估时：5–15 分钟（可选）

## 按角色的阅读捷径
- 快速上手（开发/集成）： 1 → 3 → 2 → 4 （约 1 小时）
- 安全审核（安全工程）： 1 → 6 → 7 → 2 → 8 → 3（重点深读第 6、7 篇）
- 新建/改工具（维护者/作者）： 1 → 5 → 3 → 2 → 4

## 使用建议
- 先阅读概览（第 1 篇），再按需要深读其他文档。
- 在阅读 API 规范时，将示例请求导入 Postman 或 curl 进行验证。
- 若文档存在冲突或版本差异，以最近更新的文件为准；遇到不确定条目请在仓库发起 Issue 讨论。

---

如果你同意，我已将本文件写入 docs/README.md（提交信息："docs: add README with recommended reading order for docs"）。

后续我可以：
- 把 README 的本地/在线渲染截图发送给你预览；或
- 根据你的偏好，生成一个更简洁或更详细的版本；或
- 自动把每个文档的要点（1–2 行总结）提取并加入 README 中。

请选择下一步。