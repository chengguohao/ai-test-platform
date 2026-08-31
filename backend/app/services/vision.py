"""多模态规范化：需求文档（docx 全文 + 内嵌图片）一次调用转固定模板。

设计（用户已确认）：
- 主路径只传一个 docx，图片一律内嵌在 docx 里；无独立图片上传。
- `extract_docx` 只是**机械解包**（python-docx 抽文本 + zipfile 抽内嵌图字节），
  **理解由多模态模型在一次调用里完成**——全文 + 全部图作为 content blocks 一起发，
  模型同时读文字和图，输出符合《需求文档模板》的 markdown，图片信息内联到对应功能小节。
- 副模型选择链：`Project.vision_model_id` → `ai_model_id` → 全局 .env。
- 失败不阻塞：降级保存机械抽取纯文本并注明未识图。
"""
from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy.orm import Session

from app import models, storage
from app.config import BASE_DIR
from app.services import ai_llm, task_progress

# docx 内嵌图支持的后缀 -> MIME（发给多模态 API 用）
_IMAGE_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}

# 规范化目标模板骨架（与 docs/templates/需求文档模板.md 对齐；运行时优先读真实模板文件）
_TEMPLATE_PATH = BASE_DIR / "docs" / "templates" / "需求文档模板.md"

_TEMPLATE_SKELETON = """# 需求说明书：{模块中文名}（v{版本号}）

## 一、需求背景与目标
- 背景：{一句话说明为什么做这个功能}
- 目标：{本次要达成什么效果}
- 模块英文短名（module）：{如 notice}

## 二、涉及角色与权限
- {角色中文名}（{角色英文标识}）：{该角色能做什么}

## 三、功能需求（逐条列出）
### 3.1 {功能点编号} {功能点名称}
- 入口/操作：{用户从哪个页面进入、怎么操作}
- 业务规则：{必填项、字段长度、可选值、状态流转等}
- 【图】{原型图/流程图名}：{该图的关键信息文字描述}
- 预期结果：{操作完成后用户看到的可见结果}

## 四、业务规则与约束
- 字段规则：{字段名}：{类型 / 是否必填 / 长度 / 枚举}
- 状态流转：{如 草稿 → 已发布 → 已下线}
- 权限约束：{哪些操作仅限哪些角色}

## 五、异常与边界场景
- {异常场景}：{预期行为 / 对应业务错误码 key}

## 六、验收标准
- [ ] {可验收的清单项}

## 七、待确认事项
- {疑问；没有则写"无"}"""


def _load_template() -> str:
    """读需求文档模板文件；缺失/失败时用内嵌骨架，保证提示词恒定可用。"""
    try:
        if _TEMPLATE_PATH.exists():
            return _TEMPLATE_PATH.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return _TEMPLATE_SKELETON


NORMALIZE_SYSTEM_PROMPT = (
    "你是资深测试需求文档整理专家。请把用户提供的需求文档内容（可能含正文文本 + 多张图片）"
    "规整成下面固定模板结构的 markdown，不要改变原意，只做结构化整理。\n"
    "要求：\n"
    "① 图片信息**内联**到对应功能小节（如【图】新增公告弹窗原型：弹窗含标题输入框（必填）…），"
    "把图里的按钮/字段/布局/流转关系等关键信息写成文字，图片本身不要单独罗列；\n"
    "② 字段名/接口路径/枚举值/角色标识尽量与提供的《接口文档.json》上下文对齐，冲突时以接口文档为准并注明；\n"
    "③ 不臆造：原文档缺失的信息写『待确认』，不要编造。\n\n"
    "固定模板结构：\n" + _load_template()
)


def _walk_table(table, text_parts: list[str]) -> None:
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells if c.text.strip()]
        if cells:
            text_parts.append(" | ".join(cells))


def extract_docx(path: str | Path) -> tuple[str, list[dict]]:
    """机械解包 docx：python-docx 抽段落+表格文本；zipfile 抽 word/media/* 图片字节。

    返回 (text, images)，images: [{name, bytes, mime}]（无图则空列表）。
    """
    import zipfile

    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    text_parts: list[str] = []

    # 按文档顺序遍历正文段落与表格（python-docx 的 paragraphs 不含表格内文本）
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            t = Paragraph(child, doc).text.strip()
            if t:
                text_parts.append(t)
        elif child.tag == qn("w:tbl"):
            _walk_table(Table(child, doc), text_parts)

    images: list[dict] = []
    try:
        with zipfile.ZipFile(str(path)) as zf:
            for name in zf.namelist():
                if not name.startswith("word/media/"):
                    continue
                ext = Path(name).suffix.lower()
                mime = _IMAGE_MIME.get(ext)
                if not mime:
                    continue
                images.append({"name": Path(name).name, "bytes": zf.read(name), "mime": mime})
    except Exception:  # noqa: BLE001
        pass  # 图片抽取失败不致命，纯文本仍可用
    return "\n".join(text_parts).strip(), images


def _pick_vision_config(db: Session, project_id: int | None) -> dict | None:
    """副模型选择链：vision_model_id → ai_model_id → None（全局 .env 默认）。

    被绑定模型不存在/被禁用时回退下一档；全部不可用返回 None 走全局配置。
    """
    p = db.get(models.Project, project_id) if project_id else None
    ids = [p.vision_model_id, p.ai_model_id] if p else []
    for mid in ids:
        if not mid:
            continue
        m = db.get(models.AiModelConfig, mid)
        if m and m.enabled:
            return {"base_url": m.base_url, "api_key": m.api_key,
                    "model": m.model, "temperature": m.temperature}
    return None


def normalize_requirement_async(run_id: int, project_id: int | None) -> None:
    """后台线程入口：整文档多模态规范化（进度见 req_vision:{run_id}）。

    流程：取全部 requirement 工件（md/txt 拼正文，docx 解包出正文+内嵌图）
    → 取最新 api_doc 作对齐上下文 → 一次多模态调用 → 存「需求文档（已规范化）」工件
    → 失败降级为机械纯文本，不阻塞需求流程。
    """
    from app.db import SessionLocal
    from app.services import task_progress as _tp

    db = SessionLocal()
    pkey = f"req_vision:{run_id}"
    _tp.start(pkey)
    project_name = f"p{run_id}"
    text_parts: list[str] = []
    max_version = 1
    try:
        run = db.get(models.WorkflowRun, run_id)
        if not run:
            raise ValueError(f"流程实例不存在: {run_id}")
        p = db.get(models.Project, run.project_id) if run.project_id else None
        if p:
            project_name = p.name

        # 1) 收集全部 requirement 工件：md/txt 拼正文，docx 解包
        arts = db.query(models.Artifact).filter(
            models.Artifact.run_id == run_id, models.Artifact.type == "requirement"
        ).order_by(models.Artifact.version.asc()).all()
        if not arts:
            raise ValueError("尚未上传需求工件，无法规范化")
        images: list[dict] = []
        for a in arts:
            max_version = max(max_version, a.version or 1)
            if not a.file_path or not Path(a.file_path).exists():
                continue
            if Path(a.file_path).suffix.lower() == ".docx":
                t, imgs = extract_docx(a.file_path)
                text_parts.append(t)
                images.extend(imgs)
            else:
                text_parts.append(Path(a.file_path).read_text(encoding="utf-8", errors="ignore"))
        _tp.report(pkey, f"收集需求工件 {len(arts)} 个，内嵌图片 {len(images)} 张")

        # 2) 最新 api_doc 作字段对齐上下文
        api = ""
        api_art = db.query(models.Artifact).filter(
            models.Artifact.run_id == run_id, models.Artifact.type == "api_doc"
        ).order_by(models.Artifact.version.desc()).first()
        if api_art and api_art.file_path and Path(api_art.file_path).exists():
            api = Path(api_art.file_path).read_text(encoding="utf-8", errors="ignore")

        # 3) 一次多模态调用
        llm_cfg = _pick_vision_config(db, run.project_id)
        prompt = NORMALIZE_SYSTEM_PROMPT
        if api.strip():
            prompt += f"\n\n参考的《接口文档.json》上下文：\n{api[:60000]}"
        text = "\n\n".join(x for x in text_parts if x.strip())
        if not text.strip() and not images:
            raise ValueError("需求工件没有可读文本也没有内嵌图片，无法规范化")
        _tp.report(pkey, f"调用多模态模型识别文本+图片（{len(text)} 字符正文，{len(images)} 张图）…")
        out = ai_llm.chat_multimodal(text, images, prompt=prompt, llm_config=llm_cfg)
        if not out.strip():
            raise ValueError("多模态模型返回为空")
        _tp.report(pkey, f"规范化完成，输出 {len(out)} 字符")

        # 4) 存为「需求文档（已规范化）」工件（version = 现有最大 version + 1，
        #    _latest_artifact_text 按 version desc 自动取到它）
        version = max_version + 1
        name = f"需求文档（已规范化）v{version}.md"
        path = storage.save_text(project_name, run_id, name, out, subdir="normalized")
        db.add(models.Artifact(run_id=run_id, stage_type="requirement", type="requirement",
                               name=name, file_path=str(path), version=version,
                               source={"source": "vision_normalize", "images": len(images)}))
        db.commit()
        _tp.report(pkey, f"已保存规范化需求工件「{name}」")
        storage.append_log(project_name, run_id, "vision",
                           f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 规范化成功："
                           f"正文 {len(text)} 字符 / 图片 {len(images)} 张 / 输出 {len(out)} 字符\n")
    except Exception as e:  # noqa: BLE001
        # 5) 失败降级：保存机械抽取纯文本，注明未识图，不阻塞
        try:
            text = "\n\n".join(x for x in text_parts if x.strip())
            if text.strip():
                name = f"需求文档（已规范化·降级纯文本）v{max_version + 1}.md"
                path = storage.save_text(project_name, run_id, name, text, subdir="normalized")
                db.add(models.Artifact(run_id=run_id, stage_type="requirement", type="requirement",
                                       name=name, file_path=str(path), version=max_version + 1,
                                       source={"source": "vision_fallback", "reason": str(e)}))
                db.commit()
            storage.append_log(project_name, run_id, "vision",
                               f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 规范化失败（已降级纯文本）：{e}\n")
            _tp.report(pkey, f"[降级] 多模态规范化失败，已保存机械抽取纯文本：{e}")
        except Exception:  # noqa: BLE001
            pass
        _tp.finish(pkey, error=str(e))
    else:
        _tp.finish(pkey)
    finally:
        db.close()
