-- ============================================================================
-- SmartAdmin v3：创建「填报员(reporter)/审核员(auditor)」角色与账号（RBAC 测试预置）
-- 目标库: smart_admin_v3   （MySQL 8.x）
--
-- 特性：幂等可重复执行（按 role_code / login_name 先清理再插入，不影响其他数据）
-- 约定：
--   1) 新账号初始密码与 admin 一致（复用 admin 的 Argon2id 哈希），默认都是 123456；
--   2) 新角色直接复制「技术总监(role_id=1)」的菜单权限与数据权限，保证能访问系统；
--      若后续要对账号收权（如填报员不可删、审核员只读），请在后台「系统管理→角色」调整。
-- 执行：mysql -uroot -p smart_admin_v3 < create_rbac_accounts.sql
-- ============================================================================

USE smart_admin_v3;

-- ---------------------------------------------------------------------------
-- Step 0：幂等清理（按角色 code 与账号名精确删除，避免误伤）
-- ---------------------------------------------------------------------------
-- 清理两个角色绑定的菜单/数据/用户关联
DELETE rm FROM t_role_menu rm
  JOIN t_role r ON r.role_id = rm.role_id AND r.role_code IN ('reporter', 'auditor');
DELETE rd FROM t_role_data_scope rd
  JOIN t_role r ON r.role_id = rd.role_id AND r.role_code IN ('reporter', 'auditor');
DELETE re FROM t_role_employee re
  JOIN t_role r ON r.role_id = re.role_id AND r.role_code IN ('reporter', 'auditor');
-- 清理角色本身
DELETE FROM t_role WHERE role_code IN ('reporter', 'auditor');
-- 清理两个测试账号（先清绑定，防外键残留）
DELETE re FROM t_role_employee re
  JOIN t_employee e ON e.employee_id = re.employee_id
 WHERE e.login_name IN ('reporter01', 'auditor01');
DELETE FROM t_employee WHERE login_name IN ('reporter01', 'auditor01');

-- ---------------------------------------------------------------------------
-- Step 1：创建角色
-- ---------------------------------------------------------------------------
INSERT INTO t_role (role_name, role_code, remark) VALUES
  ('填报员', 'reporter', '自动化测试角色：可新增/修改所负责的企业数据，只读其余'),
  ('审核员', 'auditor',  '自动化测试角色：只读审核阶段，不允许修改业务数据');

-- ---------------------------------------------------------------------------
-- Step 2：创建账号
--   密码摘要说明：后端登录校验基于 Argon2id + 私有变换，无法用 SQL 复现"明文密码"，
--   因此 login_pwd 直接取"后端系统生成并重置后的真实哈希"（可从 t_employee 复制）。
--   当前账号明文密码不随仓库分发：在 SmartAdmin 后台「员工管理 → 重置密码」生成后写入本机 .env（SA_ROLES_JSON），本文件仅保留 Argon2id 占位哈希。
--   （重置密码：admin 登录后台 → 系统管理 → 员工管理 → 重置密码，或用 /employee/update/password/reset/{id}）
-- ---------------------------------------------------------------------------
INSERT INTO t_employee
  (employee_uid, login_name, login_pwd, actual_name, gender, phone, department_id,
   position_id, email, disabled_flag, deleted_flag, administrator_flag, remark)
VALUES
  (REPLACE(UUID(), '-', ''), 'reporter01', '$argon2id$v=19$m=16384,t=2,p=1$2dkdd+14wBD698G90Ps0/w$C7Gq2Y1Dq5aRJFAt8gBRASoQbx8VucbKFduwgrz2N3k',
   '填报员甲', 0, '13800000001', 1, 3, NULL, 0, 0, 0, 'RBAC 测试：填报员'),
  (REPLACE(UUID(), '-', ''), 'auditor01', '$argon2id$v=19$m=16384,t=2,p=1$Pts4JSrMkXGy7v3EfZw6KA$fsQMrZkukhtVXdWou50Q+r2nkJE0cHllEgx+p2KPRE8',
   '审核员乙', 0, '13800000002', 1, 3, NULL, 0, 0, 0, 'RBAC 测试：审核员');

-- ---------------------------------------------------------------------------
-- Step 3：账号-角色绑定
-- ---------------------------------------------------------------------------
INSERT INTO t_role_employee (role_id, employee_id)
SELECT r.role_id, e.employee_id
  FROM t_role r, t_employee e
 WHERE r.role_code = 'reporter' AND e.login_name = 'reporter01';
INSERT INTO t_role_employee (role_id, employee_id)
SELECT r.role_id, e.employee_id
  FROM t_role r, t_employee e
 WHERE r.role_code = 'auditor' AND e.login_name = 'auditor01';

-- ---------------------------------------------------------------------------
-- Step 4：复制「技术总监(role_id=1)」的菜单权限与数据权限给两个新角色
--   （保证新账号可访问系统与企业模块；后续按需在后台收权）
-- ---------------------------------------------------------------------------
INSERT INTO t_role_menu (role_id, menu_id)
SELECT r2.role_id, rm.menu_id
  FROM t_role_menu rm
  JOIN t_role r1 ON r1.role_id = rm.role_id AND r1.role_id = 1
  CROSS JOIN t_role r2
 WHERE r2.role_code IN ('reporter', 'auditor');

INSERT INTO t_role_data_scope (role_id, data_scope_type, view_type)
SELECT r2.role_id, ds.data_scope_type, ds.view_type
  FROM t_role_data_scope ds
  JOIN t_role r1 ON r1.role_id = ds.role_id AND r1.role_id = 1
  CROSS JOIN t_role r2
 WHERE r2.role_code IN ('reporter', 'auditor');

-- ---------------------------------------------------------------------------
-- Step 4b：审核员收权 —— 只保留「查询/详情」，移除 新建/编辑/删除/企业员工增删 按钮权限
--   （对应菜单 182 新建 / 183 编辑 / 184 删除 / 261 添加企业员工 / 262 删除企业员工）
-- ---------------------------------------------------------------------------
DELETE rm FROM t_role_menu rm
  JOIN t_role r ON r.role_id = rm.role_id AND r.role_code = 'auditor'
 WHERE rm.menu_id IN (182, 183, 184, 261, 262);

-- ---------------------------------------------------------------------------
-- Step 5：校验输出
-- ---------------------------------------------------------------------------
SELECT '角色' AS 类型, role_id, role_name, role_code FROM t_role WHERE role_code IN ('reporter', 'auditor');
SELECT '账号' AS 类型, employee_id, login_name, actual_name, department_id FROM t_employee WHERE login_name IN ('reporter01', 'auditor01');
SELECT '绑定' AS 类型, r.role_code, e.login_name
  FROM t_role_employee re
  JOIN t_role r ON r.role_id = re.role_id
  JOIN t_employee e ON e.employee_id = re.employee_id
 WHERE r.role_code IN ('reporter', 'auditor');