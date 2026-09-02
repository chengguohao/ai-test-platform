"""被测系统画像扫描：把「生成/执行的被测系统子目录」动态解析成 skill 提示词可用的信息。

设计目标（2026-08-31 确立）：
    平台只绑定「pytest 框架工程」（pytest-bdd 的执行宿主），不绑定任何被测系统。
    被测系统子目录（tests/api/{system}/）及其 conftest / 业务码模块 / marker 全部按
    gen_dir 动态扫描，skill 提示词与执行器按画像渲染 —— 换系统只需在新建项目时填好
    gen_dir（或让默认推断生效），无需改一行代码。

画像字段含义：
    api_base       实际生效的被测系统子目录（绝对路径）
    system_name    展示名（如 SmartAdmin），用于 allure.feature 标题
    marker         主业务 marker（如 smartadmin）；None 表示无可推断 marker，执行时不加 -m
    codes_var     业务码常量名（如 SA_CODES）；None = 该工程无业务码表
    codes_mod      业务码所在模块名（如 smartadmin → support.fixtures.smartadmin）
    has_roles      是否具备角色体系（conftest 继承链真的提供 role_registry/admin_client）
    markers        --strict-markers 下该工程全部已注册 marker（LLM 只能使用这些，禁止自造）
    fixtures       gen_dir 继承链上 conftest 实际注册的 fixture 名（LLM 只能使用这些）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings

# conftest fixture 的两种注册形式
_FIXTURE_DECORATOR = re.compile(r"@pytest\.fixture[^\n]*\s*\n\s*def\s+(\w+)")
_FIXTURE_ASSIGN = re.compile(r"^(\w+)\s*=\s*pytest\.fixture", re.M)
# 模块级业务码常量：优先 dict 类型表（SA_CODES: dict），避坑 list 型的 SA_UNAUTHORIZED_CODES
_CODES_DICT = re.compile(r"^([A-Z][A-Z0-9_]*?CODES)\s*:\s*dict", re.M)
_CODES_ANY = re.compile(r"^([A-Z][A-Z0-9_]*?CODES)\s*[:=]", re.M)
# 通用 marker（不属于任何被测系统，不能当主业务 marker）
_GENERIC_MARKERS = {"api", "acceptance", "smoke", "slow", "requires_role"}
# 已生成用例文件里的 marker（用于从现存用例反推本系统实际 marker）
_MK_IN_FILE = re.compile(r"@pytest\.mark\.(\w+)")
# 系统子目录名 → 展示名美化
_PRETTY_NAME = {"smartadmin": "SmartAdmin"}


@dataclass
class SystemProfile:
    system_name: str = "被测系统"
    marker: str | None = None
    codes_var: str | None = None
    codes_mod: str | None = None
    has_roles: bool = False
    markers: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    api_base: Path | None = None
    available_roles: list[str] = field(default_factory=list)   # .env 已配置角色账号的角色键（生成时约束 requires_role）

    @property
    def codes_import(self) -> str | None:
        """可抄进生成脚本的 import 行；无业务码表时为 None。"""
        if self.codes_var and self.codes_mod:
            return f"from support.fixtures.{self.codes_mod} import {self.codes_var}"
        return None


def default_api_base(project_dir: Path) -> Path:
    """gen_dir 未填时的默认被测系统子目录：tests/api 下唯一子目录优先，否则回退 smartadmin。
    与 collect_system_profile 保持一致（单独抽出，供不依赖完整画像的早期判断使用）。"""
    api_root = project_dir / "tests" / "api"
    if api_root.is_dir():
        subs = sorted(p for p in api_root.iterdir() if p.is_dir())
        if len(subs) == 1:
            return subs[0]
    return project_dir / "tests" / "api" / "smartadmin"


def resolve_target_file(engine: dict, module: str, target_file: str) -> Path | None:
    """把用户填写的「目标脚本文件」解析为绝对路径（生成与执行共用同一规则）。

    - 空 / 全空白            → 返回 None，调用方走默认（生成写 test_{module}.py；执行跑整个模块目录）
    - 纯文件名（无路径分隔符）→ {api_base}/{module}/{文件名}（与被测系统子目录 conftest 保持一致）
    - 含路径分隔符或以 . 开头 → 相对 pytest 项目根解析（支持 tests/api/xxx/test_yy.py 这类路径）

    强制校验：必须以 .py 结尾；解析后必须落在 pytest 项目目录内（防目录穿越）。
    非法输入抛 ValueError，接口层转为 422 提示。
    """
    raw = (target_file or "").strip().replace("\\", "/")
    if not raw:
        return None
    if not raw.endswith(".py"):
        raise ValueError(f"目标文件必须以 .py 结尾：{raw!r}")
    project_dir = Path(engine.get("pytest_project_dir") or settings().PYTEST_PROJECT_DIR)
    if "/" in raw or raw.startswith("."):
        path = project_dir / raw
    else:
        api_base = collect_system_profile(engine).api_base
        path = api_base / module / raw
    resolved = path.resolve()
    if not resolved.is_relative_to(project_dir.resolve()):
        raise ValueError(f"目标文件必须在 pytest 项目目录内：{raw!r}")
    return resolved


def _conftest_chain(target_dir: Path, project_dir: Path) -> list[Path]:
    """收集生成文件所在目录到项目根的 conftest 继承链（从近到远）。

    pytest 的 fixture 作用域 = 文件所在目录 + 各级祖先 conftest 的并集；
    只收链上的 conftest（不再全项目 rglob，避免把兄弟系统子目录的 fixture 混进来）。
    """
    chain: list[Path] = []
    d = target_dir
    while True:
        cf = d / "conftest.py"
        if cf.is_file():
            chain.append(cf)
        if d == project_dir or d.parent == d:
            break
        d = d.parent
    return chain


def _collect_fixtures(conftests: list[Path]) -> list[str]:
    """从给定 conftest 链解析实际注册的 fixture 名（装饰器 + 赋值注册两种形式）。"""
    names: set[str] = set()
    for cf in conftests:
        try:
            t = cf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        names.update(_FIXTURE_DECORATOR.findall(t))
        names.update(_FIXTURE_ASSIGN.findall(t))
    return sorted(names)


def _scan_markers(project_dir: Path) -> list[str]:
    """读取工程注册的 marker 名（pyproject.toml 数组 / pytest.ini / setup.cfg）。"""
    names: set[str] = set()
    for c in (project_dir / "pyproject.toml", project_dir / "pytest.ini",
              project_dir / "setup.cfg", project_dir / "tox.ini"):
        if not c.is_file():
            continue
        text = c.read_text(encoding="utf-8", errors="ignore")
        # TOML 数组元素 "name: desc"（跨行也命中）与 ini 的 "name : desc" 行
        names.update(re.findall(r'"(\w+)\s*:', text))
        for m in re.finditer(r'^\s*(\w+)\s*:', text, re.M):
            names.add(m.group(1))
    return sorted(names)


def collect_system_profile(engine: dict, module: str = "") -> SystemProfile:
    """按项目引擎配置扫描被测系统画像。engine 来自 Project.engine_config。"""
    project_dir = Path(engine.get("pytest_project_dir") or settings().PYTEST_PROJECT_DIR)
    explicit = (engine.get("gen_dir") or "").strip()
    if explicit:
        api_base = Path(explicit).expanduser()
        if not api_base.is_absolute():
            api_base = project_dir / api_base
    else:
        api_base = default_api_base(project_dir)
    prof = SystemProfile()
    prof.api_base = api_base
    prof.markers = _scan_markers(project_dir)

    # fixture：生成文件落在 {api_base}/{module}/，链起点从该目录向上收
    target_dir = api_base / module if module else api_base
    prof.fixtures = _collect_fixtures(_conftest_chain(target_dir, project_dir))

    # 业务码：从工程 support/fixtures/*.py 扫描，名字匹配系统子目录者优先
    prof.system_name = _PRETTY_NAME.get(api_base.name, api_base.name[:1].upper() + api_base.name[1:])
    fixtures_dir = project_dir / "support" / "fixtures"
    candidates: list[tuple[str, str]] = []   # (module_name, codes_var)
    if fixtures_dir.is_dir():
        for mod in sorted(fixtures_dir.glob("*.py")):
            if mod.name == "__init__.py":
                continue
            t = mod.read_text(encoding="utf-8", errors="ignore")
            m = _CODES_DICT.search(t) or _CODES_ANY.search(t)
            if m:
                candidates.append((mod.stem, m.group(1)))
    for mod_stem, codes_var in candidates:
        if mod_stem == api_base.name:
            prof.codes_var, prof.codes_mod = codes_var, mod_stem
            break
    else:
        if candidates:
            prof.codes_var, prof.codes_mod = candidates[0]
    # 角色体系以 fixture 事实为准：conftest 继承链真的提供 role_registry/admin_client 才认为具备
    prof.has_roles = "role_registry" in prof.fixtures and "admin_client" in prof.fixtures
    # 可用角色：.env SA_ROLES_JSON 里已配置且有密码的角色键（防生成脚本引用未配置角色导致整模块 skip）
    prof.available_roles = _scan_available_roles(project_dir)

    # 主 marker：系统子目录名在注册表内优先；否则从该子目录现存用例反推；再否则 None
    # （None = 执行时不加 -m，靠目录限定收集；绝不能用其它系统的 marker 误过滤）
    if api_base.name in prof.markers:
        prof.marker = api_base.name
    elif api_base.is_dir():
        prof.marker = _detect_file_marker(api_base)
    return prof


def _scan_available_roles(project_dir: Path) -> list[str]:
    """读取 pytest 工程 .env 的 SA_ROLES_JSON，返回已配置且有密码的角色键。

    与 pytest-bdd/support/fixtures/smartadmin.py::load_sa_roles 同源：
    未配置时回退单 admin。供生成侧约束 requires_role / FlowStep role 使用，
    避免生成脚本引用未配置角色导致整模块 skip。
    """
    env_file = project_dir / ".env"
    roles: list[str] = []
    if env_file.is_file():
        raw = ""
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("SA_ROLES_JSON="):
                raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
        if raw:
            try:
                parsed = json.loads(raw)
                roles = [k for k, v in parsed.items()
                         if isinstance(v, dict) and (v.get("password") or "").strip()]
            except Exception:  # noqa: BLE001 解析失败回退单 admin
                roles = []
    return roles or ["admin"]


def _detect_file_marker(api_base: Path) -> str | None:
    """从被测系统子目录现存 test_*.py 反推其实际使用的业务 marker（排除通用 marker）。"""
    from collections import Counter
    cnt: Counter = Counter()
    for f in api_base.rglob("test_*.py"):
        try:
            t = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _MK_IN_FILE.findall(t):
            if m not in _GENERIC_MARKERS:
                cnt[m] += 1
    if not cnt:
        return None
    top, _n = cnt.most_common(1)[0]
    return top