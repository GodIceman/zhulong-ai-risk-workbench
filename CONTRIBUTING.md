# 贡献指南 / Contributing

感谢你帮助改进烛龙。这是一个保守风险分流原型，任何功能改动都必须保留“不认证真实”的产品边界。

## 提交前

1. 先搜索现有 Issue，大型改动先用 Issue 说明问题、用户价值和验收方式。
2. 不要提交真实用户媒体、评测数据、模型权重、日志、报告或凭据。
3. 第三方代码应通过固定上游版本获取，不要直接复制进主仓库。
4. 新的能力声明必须有可复核的测试或评估证据，并写明局限。

## 本地检查

```powershell
Set-Location zhulong
npm ci
npm run build
Set-Location ..
./.venv-lrfimd/Scripts/python.exe -m unittest discover -s tests -v
```

需要大型模型的运行时测试只在已完成本地模型配置的机器上运行。

## Pull request

- 保持单一、可验证的主题。
- 说明产品行为变化、验证结果、风险与局限。
- 如使用 AI 编程工具，请确保提交者已审核、理解并验证最终更改。

---

Please keep changes focused and testable. Do not submit real-user media, evaluation datasets, model weights, logs, reports, or credentials. Preserve the project's abstention-first product boundary, document limitations, and personally review any AI-assisted code before submission.
