"""
简历解析服务 — 将简历文件转为结构化数据。

流程:
    1. 读取文件 (PDF/DOCX/TXT)
    2. 调用 DeepSeek 解析为 JSON
    3. 存储结构化结果到 Resume.structured_data
"""

import json
from pathlib import Path

import structlog

from app.core.llm_client import LLMClient
from app.prompts import clean_json_response

logger = structlog.get_logger(__name__)


class ResumeParseError(Exception):
    """简历解析失败。"""


class ResumeParser:
    """
    简历解析器 — 使用 DeepSeek 将简历文件解析为结构化 JSON。
    """

    # 支持的文件类型
    SUPPORTED_TYPES = {".pdf", ".docx", ".txt", ".md"}

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    async def parse(self, file_path: str) -> dict:
        """
        解析简历文件。

        Args:
            file_path: 简历文件路径

        Returns:
            结构化简历数据

        Raises:
            ResumeParseError: 解析失败
        """
        path = Path(file_path)

        # 1. 读取文本内容
        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_TYPES:
            raise ResumeParseError(f"不支持的文件类型: {suffix}。支持: {self.SUPPORTED_TYPES}")

        raw_text = await self._extract_text(str(path), suffix)

        if not raw_text or len(raw_text.strip()) < 50:
            raise ResumeParseError("简历文本内容过短，可能文件为空或格式不支持")

        # 2. 调用 DeepSeek 解析
        try:
            structured_data = await self._parse_with_llm(raw_text)
        except Exception as exc:
            logger.error("resume_llm_parse_failed", error=str(exc))
            raise ResumeParseError(f"AI 解析失败: {exc}") from exc

        # 3. 提取技能列表（确保格式规范）
        structured_data.setdefault("personal_info", {})
        structured_data.setdefault("education", [])
        structured_data.setdefault("experience", [])
        structured_data.setdefault("projects", [])
        structured_data.setdefault("skills", [])
        structured_data.setdefault("certifications", [])

        logger.info(
            "resume_parsed",
            file=path.name,
            skills=len(structured_data["skills"]),
            experiences=len(structured_data["experience"]),
        )

        return structured_data

    async def _extract_text(self, file_path: str, suffix: str) -> str:
        """根据文件类型提取文本。"""
        # TXT / MD — 直接读取
        if suffix in (".txt", ".md"):
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()

        # PDF — 使用简单的文本提取（后续可换为 PyMuPDF 或 pdfplumber）
        if suffix == ".pdf":
            return await self._extract_pdf_text(file_path)

        # DOCX — 使用 python-docx（如可用）
        if suffix == ".docx":
            return await self._extract_docx_text(file_path)

        raise ResumeParseError(f"未实现的文本提取: {suffix}")

    async def _extract_pdf_text(self, file_path: str) -> str:
        """从 PDF 提取文本（优先 pdfplumber，中文支持最好）。"""
        # 方案 1: pdfplumber（中文支持最好）
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                texts = [page.extract_text() or "" for page in pdf.pages]
                result = "\n".join(t for t in texts if t.strip())
                if result.strip():
                    return result
        except ImportError:
            pass
        except Exception:
            pass  # 损坏的 PDF 回退到 PyPDF2

        # 方案 2: pdftotext 命令行工具
        try:
            import subprocess
            result = subprocess.run(["pdftotext", file_path, "-"], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except FileNotFoundError:
            pass

        # 方案 3: PyPDF2（英文支持好）
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            raise ResumeParseError("PDF 解析需要安装 pdfplumber、pdftotext 或 PyPDF2。请执行: pip install pdfplumber")

    async def _extract_docx_text(self, file_path: str) -> str:
        """从 DOCX 提取文本。"""
        try:
            from docx import Document
            doc = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            raise ResumeParseError("DOCX 解析需要安装 python-docx")

    async def _parse_with_llm(self, raw_text: str) -> dict:
        """使用 DeepSeek 将原始文本解析为结构化 JSON。"""
        prompt = self._build_parse_prompt(raw_text)

        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,  # 低温度，确保稳定结构化输出
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        return json.loads(clean_json_response(content))

    def _system_prompt(self) -> str:
        return """你是一位专业的简历解析专家。请将简历文本解析为以下 JSON 结构。

IMPORTANT: 所有 JSON key 必须使用英文，value 中的文本内容可以是中文或英文。

返回格式（严格遵循）：
{
  "personal_info": {"name": "", "email": "", "phone": "", "location": "", "website": "", "objective": "求职意向或自我描述"},
  "education": [{"school": "学校名", "degree": "本科/硕士/博士", "major": "专业", "start_year": "2016", "end_year": "2020"}],
  "experience": [{"company": "公司", "title": "职位", "start_date": "2020.06", "end_date": "2023.06", "description": "工作描述", "skills_used": ["Python"]}],
  "projects": [{"name": "项目名", "description": "描述", "tech_stack": ["技术"]}],
  "skills": ["Python", "FastAPI", "PostgreSQL"],
  "certifications": [{"name": "证书名", "issuer": "颁发机构"}]
}

规则：
- 所有字段未找到时设为空字符串 "" 或空数组 []
- 技能名称使用业界标准拼写（如 Python, JavaScript, Kubernetes，不要用中文）
- 时间段统一为 YYYY 或 YYYY.MM 格式
- 只返回 JSON，不要额外解释"""

    def _build_parse_prompt(self, raw_text: str) -> str:
        """构建解析 Prompt — 截断过长文本避免超出 token 限制。"""
        max_chars = 12000
        truncated = raw_text[:max_chars]
        if len(raw_text) > max_chars:
            truncated += f"\n\n... (原文共 {len(raw_text)} 字符，已截断)"

        return f"请解析以下简历文本：\n\n```\n{truncated}\n```"
