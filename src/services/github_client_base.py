"""
GitHub Client 기본 클래스: 공통 기능 제공
"""
import logging
from typing import Dict, List
from src.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class GithubClientBase:
    """
    GitHub Client의 공통 기능을 제공하는 베이스 클래스

    제공 기능:
    - HTTP 헤더 관리
    - Tree-Sitter 언어 매핑
    - 언어 감지
    - 파일 필터링
    """

    # Tree-Sitter 지원 언어와 확장자 매핑
    TREE_SITTER_LANGUAGES: Dict[str, List[str]] = {
        # Core Languages
        "bash": [".sh", ".bash", ".zsh"],
        "c": [".c", ".h"],
        "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".C", ".H"],
        "c_sharp": [".cs", ".csx"],
        "css": [".css"],
        "go": [".go"],
        "html": [".html", ".htm"],
        "java": [".java"],
        "javascript": [".js", ".jsx", ".mjs", ".cjs"],
        "json": [".json"],
        "php": [".php", ".phtml"],
        "python": [".py", ".pyw"],
        "ruby": [".rb", ".rake", ".gemspec"],
        "rust": [".rs"],
        "typescript": [".ts", ".tsx"],

        # Additional Languages
        "elixir": [".ex", ".exs"],
        "elm": [".elm"],
        "erlang": [".erl", ".hrl"],
        "fortran": [".f90", ".f95", ".f03"],
        "hack": [".hack", ".hhi"],
        "haskell": [".hs", ".lhs"],
        "hcl": [".hcl", ".tf"],
        "julia": [".jl"],
        "kotlin": [".kt", ".kts"],
        "lua": [".lua"],
        "make": ["Makefile", ".mk", ".make"],
        "markdown": [".md", ".markdown"],
        "ocaml": [".ml", ".mli"],
        "perl": [".pl", ".pm"],
        "ql": [".ql", ".qll"],
        "regex": [".regex"],
        "rst": [".rst"],
        "scala": [".scala", ".sc"],
        "sql": [".sql"],
        "toml": [".toml"],
        "yaml": [".yaml", ".yml"],

        # Specialized
        "dockerfile": ["Dockerfile", ".dockerfile"],
        "elisp": [".el"],
        "objc": [".m", ".mm"],
        "swift": [".swift"],
        "vue": [".vue"],
        "svelte": [".svelte"],
    }

    def __init__(self, token: str = None):
        """
        Args:
            token: GitHub Personal Access Token (선택)
        """
        self.headers = self._build_headers(token)

    @staticmethod
    def _build_headers(token: str = None) -> Dict[str, str]:
        """
        GitHub API 요청 헤더 생성

        Args:
            token: GitHub PAT (선택)

        Returns:
            요청 헤더 딕셔너리
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # 토큰 우선순위: 파라미터 > 설정 파일
        api_token = token or getattr(settings, 'GITHUB_TOKEN', None)
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        return headers

    @classmethod
    def is_tree_sitter_supported(cls, file_path: str) -> bool:
        """
        파일이 Tree-Sitter에서 지원하는 언어인지 확인

        Args:
            file_path: 파일 경로 (예: "src/main.py")

        Returns:
            True if supported, False otherwise
        """
        # 숨김 파일 제외
        if "/." in file_path or file_path.startswith("."):
            return False

        filename = file_path.split("/")[-1]

        # 각 언어의 확장자 목록과 비교
        for language, extensions in cls.TREE_SITTER_LANGUAGES.items():
            for ext in extensions:
                # 확장자가 점으로 시작하는 경우 (예: ".py")
                if ext.startswith("."):
                    if file_path.lower().endswith(ext.lower()):
                        return True
                # 특정 파일명인 경우 (예: "Makefile", "Dockerfile")
                else:
                    if filename == ext or filename.lower() == ext.lower():
                        return True

        return False

    @classmethod
    def detect_language(cls, file_path: str) -> str:
        """
        파일 경로에서 Tree-Sitter 언어 감지

        Args:
            file_path: 파일 경로 (예: "src/main.py")

        Returns:
            언어 이름 (예: "python") 또는 "unknown"
        """
        filename = file_path.split("/")[-1]

        for language, extensions in cls.TREE_SITTER_LANGUAGES.items():
            for ext in extensions:
                if ext.startswith("."):
                    if file_path.lower().endswith(ext.lower()):
                        return language
                else:
                    if filename == ext or filename.lower() == ext.lower():
                        return language

        return "unknown"

    @staticmethod
    def clean_zip_path(zip_path: str) -> str:
        """
        ZIP 파일 내 경로에서 최상위 폴더명 제거

        Args:
            zip_path: ZIP 내 경로 (예: "repo-abc123/src/main.py")

        Returns:
            정리된 경로 (예: "src/main.py")
        """
        parts = zip_path.split("/")
        if len(parts) > 1:
            return "/".join(parts[1:])
        return ""
