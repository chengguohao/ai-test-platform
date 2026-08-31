# language: zh-CN
@smartadmin @acceptance
功能: SmartAdmin 登录

  作为测试经理，我希望将登录协议沉淀为可评审的 Gherkin 场景，
  便于后续 AI 流水线按「需求文档 → 手工用例 → AI 生成 .feature」模式直接复用。

  背景:
    假如 我已拥有 SmartAdmin 的管理员账号密码

  场景: 正确账号密码登录成功（dev 明文验证码自动解）
    当 我发起 登录 请求，使用管理员的 正确 账号密码组合
    那么 业务信封 返回 成功 即 ok=true 且 code=0

  场景: 错误密码登录失败
    当 我发起 登录 请求，使用管理员的 错误 账号密码组合
    那么 业务信封 返回 失败，即 ok=false，且 code 不等于 0
