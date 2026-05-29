"""
AI service：封装所有 Claude API 调用。

职责（面试可复述）：
和 services/s3.py 同一个思路 —— 把第三方依赖（这里是 Anthropic SDK）关在
一个边界里。router 只调 summarize_document() 一个函数，出错只捕获本模块的
异常，完全不需要知道 anthropic SDK 内部长什么样。

关键技术点：Claude 原生支持 PDF 和图片输入，我们不用自己做 OCR / 文字提取 ——
直接把文件字节 base64 编码塞进 content block，Claude 会把每页当"图像+文字"理解。
"""
import base64

import anthropic

from config import settings

# 模型选型：Sonnet 在"质量/成本"间平衡，适合给律师看的摘要。
# 想更省 → "claude-haiku-4-5-20251001"；想最强 → "claude-opus-4-8"。
# 抽成常量，将来换模型只改这一行。
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

# Claude 能直接读的图片类型
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# 系统提示：给 Claude 设定"身份"和领域，让摘要贴合交通辩护场景。
_SYSTEM_PROMPT = (
    "You are a paralegal assistant for a Manitoba traffic-defense law firm. "
    "You review documents attached to case files and write concise, factual "
    "summaries for the supervising lawyer. Manitoba traffic offences fall under "
    "the Highway Traffic Act (HTA). Be precise and never invent facts that are "
    "not present in the document."
)

# 用户提示：明确要 Claude 抽哪些字段，没有的就省略、不要瞎编。
_USER_PROMPT = (
    "Summarize this document for the case file. In 3-6 sentences, capture: "
    "(1) what kind of document this is; (2) the alleged offence or subject matter; "
    "(3) key dates (offence date, court/hearing date); (4) the fine or amount if "
    "stated; (5) anything a defense lawyer should note (issuing officer, location, "
    "procedural details). If a field is not present, omit it rather than guessing."
)


class AIServiceError(Exception):
    """本服务对外抛出的异常基类，屏蔽 anthropic SDK 的内部异常类型。"""


class UnsupportedFileTypeError(AIServiceError):
    """文件类型无法生成摘要（如 docx/zip）。router 会把它翻译成 422。"""


# 进程级单例 client，从 settings 读 key。
_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _build_document_block(file_bytes: bytes, mime_type: str) -> dict:
    """
    根据文件类型，构造 Claude 能识别的 content block。
    - PDF   → document block（base64）
    - 图片   → image block（base64）
    - 纯文本 → 直接当文字塞进 text block
    其他类型暂不支持，抛 UnsupportedFileTypeError。
    """
    if mime_type == "application/pdf":
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(file_bytes).decode("utf-8"),
            },
        }
    if mime_type in _IMAGE_TYPES:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64.standard_b64encode(file_bytes).decode("utf-8"),
            },
        }
    if mime_type == "text/plain":
        return {"type": "text", "text": file_bytes.decode("utf-8", errors="replace")}

    raise UnsupportedFileTypeError(f"无法对该类型生成摘要: {mime_type}")


def summarize_document(file_bytes: bytes, mime_type: str) -> str:
    """
    把文档发给 Claude，返回一段摘要文本。
    流程：①按类型构造 content block → ②调 Messages API → ③拼接返回的文字块。
    """
    document_block = _build_document_block(file_bytes, mime_type)
    try:
        message = _client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        document_block,
                        {"type": "text", "text": _USER_PROMPT},
                    ],
                }
            ],
        )
    except anthropic.APIError as exc:
        # 网络错 / 额度不足 / key 无效等都会到这里
        raise AIServiceError(f"调用 Claude API 失败: {exc}") from exc

    # 返回的 content 是若干 block，把所有文字块拼起来
    summary = "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()
    if not summary:
        raise AIServiceError("Claude 返回了空摘要")
    return summary
