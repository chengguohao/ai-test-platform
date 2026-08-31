# language: zh-CN
@smartadmin @acceptance
功能: SmartAdmin OA-企业接口 CRUD（BDD 评审场景）

  作为测试经理，我希望把企业模块的核心业务流沉淀为 BDD 场景 + 场景大纲 + Examples 参数化，
  这样后续 AI 流水线能直接拿手工用例评审稿自动生成 feature + steps。

  背景:
    假如 SmartAdmin 会话已经完成登录（由 api_client fixture session 级自动登录）

  场景大纲: 创建企业后按名称关键字分页查询可命中
    当 我调用 企业 创建接口，入参 企业名="<企业名>"，联系人="<联系人>"，手机号="<手机号>"
    那么 创建 业务信封成功，保存 ent_id 到上下文，并且注册清理
    当 我调用 企业 分页查询接口，关键字="<企业名>"，pageSize=10
    那么 分页 业务信封成功，返回 total>=1，且第 1 条记录企业名包含 "<企业名>"

    例子: 两组企业样例（MVP 跑 2 组，证明场景大纲参数化有效）
      | 企业名                     | 联系人 | 手机号       |
      | SA_BDD_企业A_${ts_token}   | 王大锤 | 13800000001 |
      | SA_BDD_企业B_${ts_token}   | 奥巴马 | 13800000002 |
