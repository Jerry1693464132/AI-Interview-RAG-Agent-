"""
Prompt 模板管理 — 集中管理、支持版本号、从 YAML 文件加载。

设计原则:
    - Prompt 禁止硬编码在业务代码中
    - 每个 Prompt 模板包含: 名称、版本、内容、变量占位符
    - 支持运行时变量注入

目录结构:
    app/prompts/
    ├── __init__.py          # 加载器
    ├── resume_parse.yaml    # 简历解析 Prompt
    ├── profile_extract.yaml # 画像提取 Prompt
    ├── question_gen.yaml    # 题目生成 Prompt
    ├── scoring.yaml         # 评分 Prompt
    └── report_gen.yaml      # 报告生成 Prompt

用法:
    from app.prompts import PromptLoader

    loader = PromptLoader()
    prompt = loader.get("scoring", version="v1")
    filled = prompt.format(
        question="...",
        answer="...",
        reference_answer="...",
        key_points=["...", "..."],
    )
"""

from pathlib import Path
from typing import Any, Optional

import structlog
import yaml

logger = structlog.get_logger(__name__)


class PromptTemplate:
    """单个 Prompt 模板。"""

    def __init__(self, name: str, version: str, content: str, variables: list[str]) -> None:
        self.name = name
        self.version = version
        self.content = content
        self.variables = variables

    def format(self, **kwargs: Any) -> str:
        """
        填充模板变量，返回最终 Prompt。

        自动验证所有必需变量是否已提供。
        """
        missing = [v for v in self.variables if v not in kwargs]
        if missing:
            raise ValueError(
                f"Prompt '{self.name}' (v{self.version}) missing variables: {missing}"
            )
        return self.content.format(**kwargs)

    def __repr__(self) -> str:
        return f"<PromptTemplate name={self.name} version={self.version}>"


class PromptLoader:
    """
    Prompt 模板加载器 — 从 YAML 文件目录加载。

    每个 YAML 文件格式:
        prompts:
          - name: "scoring"
            version: "v1"
            description: "评分 Prompt"
            variables: ["question", "answer", "reference_answer", "key_points"]
            template: |
              你是一位资深面试官。请对以下回答进行评分...
    """

    def __init__(self, prompt_dir: Optional[str] = None) -> None:
        if prompt_dir is None:
            prompt_dir = str(Path(__file__).parent)
        self.prompt_dir = Path(prompt_dir)
        self._prompts: dict[str, dict[str, PromptTemplate]] = {}
        self._load_all()

    def _load_all(self) -> None:
        """加载目录下所有 YAML 文件。"""
        for yaml_file in self.prompt_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                for prompt_cfg in data.get("prompts", []):
                    template = PromptTemplate(
                        name=prompt_cfg["name"],
                        version=prompt_cfg["version"],
                        content=prompt_cfg["template"].strip(),
                        variables=prompt_cfg.get("variables", []),
                    )
                    self._prompts.setdefault(prompt_cfg["name"], {})[
                        prompt_cfg["version"]
                    ] = template
                logger.info("prompts_loaded", file=yaml_file.name)
            except Exception as exc:
                logger.error("prompt_load_error", file=str(yaml_file), error=str(exc))

    def get(self, name: str, *, version: str = "v1") -> PromptTemplate:
        """
        获取指定名称和版本的 Prompt 模板。

        Raises:
            KeyError: 模板不存在
        """
        if name not in self._prompts:
            raise KeyError(f"Prompt '{name}' not found. Available: {list(self._prompts.keys())}")
        if version not in self._prompts[name]:
            available = list(self._prompts[name].keys())
            raise KeyError(f"Version '{version}' not found for '{name}'. Available: {available}")
        return self._prompts[name][version]

    def list_prompts(self) -> list[dict[str, str]]:
        """列出所有已加载的 Prompt 模板。"""
        return [
            {"name": name, "version": version}
            for name, versions in self._prompts.items()
            for version in versions
        ]


# 全局单例
_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """获取 PromptLoader 单例。"""
    global _loader
    if _loader is None:
        _loader = PromptLoader()
    return _loader
