-- ============================================================================
-- SmartAdmin v3：创建「员工(employee)」角色与账号（RBAC 测试预置 · 通知公告员工端可见性）
-- 目标库: smart_admin_v3   （MySQL 8.x）
--
-- 特性：幂等可重复执行（按 role_code / login_name 先清理再插入，不影响其他数据）
-- 约定：
--   1) new 账号 login_pwd 复用「审核员 auditor01」的实时 Argon2id 哈希，
--      因此明文密码与 auditor01 完全一致（明文密码由后台重置产生，仅存于本机 .env，不随仓库分发）；
--      若 auditor01 密码在后台被重置过，本脚本会随之继承新哈希，两侧始终一致。
--   2) new 角色复制「技术总监(role_id=1)」的菜单权限与数据权限，保证能访问系统
--      与公告模块（含员工端 /oa/notice/employee/* 接口）。
-- 执行：mysql -uroot -p smart_admin_v3 < create_employee_role.sql
-- ============================================================================

USE smart_admin_v3;

-- ---------------------------------------------------------------------------
-- Step 0：幂等清理（按角色 code 与账号名精确删除，避免误伤）
-- ---------------------------------------------------------------------------
-- 清理 employee 角色绑定的菜单/数据/用户关联
DELETE rm FROM t_role_menu rm
  JOIN t_role r ON r.role_id = rm.role_id AND r.role_code = 'employee';
DELETE rd FROM t_role_data_scope rd
  JOIN t_role r ON r.role_id = rd.role_id AND r.role_code = 'employee';
DELETE re FROM t_role_employee re
  JOIN t_role r ON r.role_id = re.role_id AND r.role_code = 'employee';
-- 清理角色本身
DELETE FROM t_role WHERE role_code = 'employee';
-- 清理 employee01 账号（先清绑定，防外键残留）
DELETE re FROM t_role_employee re
  JOIN t_employee e ON e.employee_id = re.employee_id
 WHERE e.login_name = 'employee01';
DELETE FROM t_employee WHERE login_name = 'employee01';

-- ---------------------------------------------------------------------------
-- Step 1：创建角色
-- ---------------------------------------------------------------------------
INSERT INTO t_role (role_name, role_code, remark) VALUES
  ('员工', 'employee', '自动化测试角色：员工端，仅可见/查看对全员可见的公告');

-- ---------------------------------------------------------------------------
-- Step 2：创建账号
--   密码摘要先复用 auditor01 的实时哈希作为占位。
--   ⚠️ 正式可用密码以「admin 后台重置密码」为唯一权威（明文密码不随仓库分发，
--     通过 GET /employee/update/password/reset/{employeeId} 返回新密码并落库）。
--   .env 的 employee01 密码必须与后台重置结果一致，勿依赖本条 INSERT 的占位哈希。
-- ---------------------------------------------------------------------------
INSERT INTO t_employee
  (employee_uid, login_name, login_pwd, actual_name, gender, phone, department_id,
   position_id, email, disabled_flag, deleted_flag, administrator_flag, remark)
SELECT REPLACE(UUID(), '-', ''), 'employee01', a.login_pwd,
       '员工丙', 0, '13800000003', a.department_id, a.position_id, NULL, 0, 0, 0, 'RBAC 测试：员工'
  FROM t_employee a
 WHERE a.login_name = 'auditor01';

-- ---------------------------------------------------------------------------
-- Step 3：账号-角色绑定
-- ---------------------------------------------------------------------------
INSERT INTO t_role_employee (role_id, employee_id)
SELECT r.role_id, e.employee_id
  FROM t_role r, t_employee e
 WHERE r.role_code = 'employee' AND e.login_name = 'employee01';

-- ---------------------------------------------------------------------------
-- Step 4：复制「技术总监(role_id=1)」的菜单权限与数据权限给 employee 角色
--   （保证能访问系统与公告模块，含员工端查询/查看接口；后续可按需后台收权）
-- ---------------------------------------------------------------------------
INSERT INTO t_role_menu (role_id, menu_id)
SELECT r2.role_id, rm.menu_id
  FROM t_role_menu rm
  JOIN t_role r1 ON r1.role_id = rm.role_id AND r1.role_id = 1
  CROSS JOIN t_role r2
 WHERE r2.role_code = 'employee';

INSERT INTO t_role_data_scope (role_id, data_scope_type, view_type)
SELECT r2.role_id, ds.data_scope_type, ds.view_type
  FROM t_role_data_scope ds
  JOIN t_role r1 ON r1.role_id = ds.role_id AND r1.role_id = 1
  CROSS JOIN t_role r2
 WHERE r2.role_code = 'employee';

-- ---------------------------------------------------------------------------
-- Step 5：校验输出
-- ---------------------------------------------------------------------------
SELECT '角色' AS 类型, role_id, role_name, role_code FROM t_role WHERE role_code = 'employee';
SELECT '账号' AS 类型, employee_id, login_name, actual_name, department_id FROM t_employee WHERE login_name = 'employee01';
SELECT '绑定' AS 类型, r.role_code, e.login_name
  FROM t_role_employee re
  JOIN t_role r ON r.role_id = re.role_id
  JOIN t_employee e ON e.employee_id = re.employee_id
 WHERE r.role_code = 'employee';