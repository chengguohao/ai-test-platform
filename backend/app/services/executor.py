"""执行引擎：环境自检 → pytest 子进程 → Allure 报告 → 失败分级。

复用 pytest-bdd 工具链（pytest + allure CLI），平台只做编排与结果收集。
"""
from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from app.config import settings
from app.services.system_profile import collect_system_profile


def _read_pytest_env(project_dir: Path) -> dict:
    """读 pytest 项目内置 .env（KEY=VALUE），供环境自检判断被测系统配置是否可用。"""
    env_file = project_dir / ".env"
    out: dict[str, str] = {}
    if not env_file.exists():
        return out
    try:
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


# ---------------- 环境自检 ----------------
def env_check(engine: dict) -> dict:
    """检查被测系统与执行工具链是否就绪，区分「环境问题」与用例问题。"""
    checks: dict = {"ok": True, "items": []}

    def add(name: str, ok: bool, detail: str):
        checks["items"].append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            checks["ok"] = False

    project_dir = Path(engine.get("pytest_project_dir") or settings().PYTEST_PROJECT_DIR)
    python = engine.get("python") or str(settings().PYTEST_PYTHON)
    allure = Path(engine.get("allure_bin") or settings().ALLURE_BIN)
    base_url = engine.get("base_url", "")
    # 项目未配置 base_url 时，探测 pytest 项目内置 .env（SA_BASE_URL/SA_PASSWORD），
    # 有则视为可用（执行子进程 cwd=pytest 项目，会自动加载其 .env）
    if not base_url:
        builtin = _read_pytest_env(project_dir)
        if builtin.get("SA_BASE_URL"):
            add("被测系统地址已配置", True,
                f"使用 pytest 项目内置配置（{builtin['SA_BASE_URL']}）")
            base_url = builtin["SA_BASE_URL"]
        else:
            add("被测系统地址已配置", False, "未配置 base_url（平台与 pytest 项目 .env 均无）")
    else:
        add("被测系统地址已配置", True, base_url)
    if base_url:
        try:
            import httpx
            r = httpx.get(base_url.rstrip("/"), timeout=5.0)
            add("被测系统可连通", r.status_code < 500, f"HTTP {r.status_code}")
        except Exception as e:
            add("被测系统可连通", False, f"连接失败: {e}")
    add("pytest 项目目录存在", project_dir.exists(), str(project_dir))
    add("python 解释器存在", Path(python).exists(), python)
    add("allure CLI 存在", allure.exists(), str(allure))
    pwd = engine.get("password") or os.getenv("SA_PASSWORD", "")
    if not pwd:
        pwd = _read_pytest_env(project_dir).get("SA_PASSWORD", "")
    add("登录密码已配置", bool(pwd),
        "已配置" + ("（pytest 项目内置）" if not engine.get("password") and pwd else "")
        if pwd else "未配置 SA_PASSWORD（用例会 SKIP）")
    return checks


# ---------------- pytest 执行 ----------------
def run_pytest(engine: dict, module: str, run_workspace: Path) -> dict:
    """在 pytest-bdd 项目里子进程跑 tests/api/{module}，落 allure-results + junitxml。"""
    project_dir = Path(engine.get("pytest_project_dir") or settings().PYTEST_PROJECT_DIR)
    python = engine.get("python") or str(settings().PYTEST_PYTHON)
    allure_dir = run_workspace / "allure-results"
    junit = run_workspace / "junit.xml"
    allure_dir.mkdir(parents=True, exist_ok=True)

    # 把被测系统配置注入子进程环境（让 conftest 能登录）
    env = dict(os.environ)
    if engine.get("base_url"):
        env["SA_BASE_URL"] = engine["base_url"]
    if engine.get("login_name"):
        env["SA_LOGIN_NAME"] = engine["login_name"]
    if engine.get("password"):
        env["SA_PASSWORD"] = engine["password"]

    # 生成目录与执行目标保持一致：由被测系统画像决定（gen_dir 显式配置优先，
    # 未填则按 tests/api 子目录推断），该子目录 conftest 提供 api_client/ctx/cleanup_registry 等 fixture
    profile = collect_system_profile(engine, module)
    api_base = profile.api_base
    target = api_base / module
    cmd = [python, "-m", "pytest", str(target)]
    # 主业务 marker 按画像推断（smartadmin / 新系统自定义 marker）；无则不按 marker 过滤
    if profile.marker:
        cmd += ["-m", profile.marker]
    cmd += ["-q", "--tb=short",
            "--junitxml", str(junit),
            "--alluredir", str(allure_dir), "--clean-alluredir"]
    try:
        # Windows 下子进程输出为系统代码页（GBK），errors=replace 防止解码崩溃丢全部输出
        proc = subprocess.run(cmd, cwd=str(project_dir), env=env,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=1800)
        stdout = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": "pytest 执行超时（>30min）", "allure_dir": str(allure_dir)}
    except Exception as e:
        return {"status": "failed", "error": f"启动 pytest 失败: {e}", "allure_dir": str(allure_dir)}

    summary = _parse_junit(junit)
    # 失败分级：环境型失败（连不上/找不到模块）单独标记
    failed = summary.get("failures", 0) + summary.get("errors", 0)
    return {
        "status": "passed" if (proc.returncode == 0 and failed == 0) else "failed",
        "exit_code": proc.returncode,
        "summary": summary,
        "allure_dir": str(allure_dir),
        "error_log": stdout[-12000:],
    }


def _parse_junit(junit_path: Path) -> dict:
    if not junit_path.exists():
        return {"total": 0, "passed": 0, "failures": 0, "errors": 0, "skipped": 0}
    try:
        root = ET.parse(junit_path).getroot()
        # pytest 的 junitxml：统计在 <testsuite> 子节点上，根 <testsuites> 没有这些属性
        suites = root.findall("testsuite") or ([root] if root.tag == "testsuite" else [])
        totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        for s in suites:
            for k in totals:
                totals[k] += int(s.get(k, 0) or 0)
        totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
        return {"total": totals["tests"], "passed": totals["passed"],
                "failures": totals["failures"], "errors": totals["errors"],
                "skipped": totals["skipped"]}
    except Exception:
        return {"total": 0, "passed": 0, "failures": 0, "errors": 0, "skipped": 0}


def generate_allure(allure_dir: Path, report_dir: Path) -> tuple[Path, str]:
    """生成 Allure 报告。返回 (报告目录, CLI 输出)——输出供执行日志落盘排查。"""
    allure_bin = Path(settings().ALLURE_BIN)
    cmd = [str(allure_bin), "generate", str(allure_dir), "-o", str(report_dir), "--clean"]
    # 同上：GBK 输出防解码崩溃
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    _inject_chinese_locale(report_dir)
    return report_dir, output


def _inject_chinese_locale(report_dir: Path) -> None:
    """Allure 报告默认英文。注入脚本在 app.js 加载前把语言设为中文(zh)。"""
    idx = report_dir / "index.html"
    if not idx.exists():
        return
    snippet = (
        '<script>try{var s=JSON.parse(localStorage.getItem("ALLURE_REPORT_SETTINGS")||"{}");'
        'if(s.language!=="zh"){s.language="zh";'
        'localStorage.setItem("ALLURE_REPORT_SETTINGS",JSON.stringify(s));}}catch(e){}</script>'
    )
    html = idx.read_text(encoding="utf-8", errors="ignore")
    if "ALLURE_REPORT_SETTINGS" not in html:
        html = html.replace("</head>", snippet + "</head>", 1)
        idx.write_text(html, encoding="utf-8")


def parse_junit_cases(junit_path: Path) -> list[dict]:
    """解析 junit.xml 为逐用例结果，供平台展示中文结构化执行明细。"""
    cases: list[dict] = []
    if not junit_path.exists():
        return cases
    try:
        root = ET.parse(junit_path).getroot()
        suites = root.findall("testsuite") or ([root] if root.tag == "testsuite" else [])
        for s in suites:
            for tc in s.findall("testcase"):
                fail = tc.find("failure")
                err = tc.find("error")
                skip = tc.find("skipped")
                if fail is not None or err is not None:
                    status = "失败" if fail is not None else "错误"
                elif skip is not None:
                    status = "跳过"
                else:
                    status = "通过"
                cases.append({
                    "name": tc.get("name", ""),
                    "status": status,
                    "time": float(tc.get("time", 0) or 0),
                })
    except Exception:
        pass
    return cases
