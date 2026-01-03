from typing import List, Optional
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language
from src.models.github import GithubFileObject
from src.models.search import CodeChunk
from src.chunking.java_method_chunker import JavaMethodChunker
import logging
import re

logger = logging.getLogger(__name__)


class CodeChunker:
    """
    1. Langchain Text-Splitter가 제공하는 25개 언어 (LangChain 전체 활용)
    2. 동적 청크 크기: 파일 크기에 따라 자동 조정
    3. Context 정보 주입: 저장소/브랜치/함수명
    """

    LANGUAGE_MAP = {
        "python": Language.PYTHON,
        "java": Language.JAVA,
        "javascript": Language.JS,
        "typescript": Language.TS,
        "go": Language.GO,
        "cpp": Language.CPP,
        "html": Language.HTML,
        "c": Language.C,
        "c_sharp": Language.CSHARP,
        "kotlin": Language.KOTLIN,
        "php": Language.PHP,
        "ruby": Language.RUBY,
        "rust": Language.RUST,
        "scala": Language.SCALA,
        "swift": Language.SWIFT,
        "markdown": Language.MARKDOWN,
        "rst": Language.RST,
        "lua": Language.LUA,
        "perl": Language.PERL,
        "haskell": Language.HASKELL,
        "elixir": Language.ELIXIR,
        "proto": Language.PROTO,
        "sol": Language.SOL,
        "cobol": Language.COBOL,
        "latex": Language.LATEX,
    }

    # 파일 크기별 청크 설정
    SIZE_THRESHOLDS = {
        "tiny": (0, 500),
        "small": (500, 2000),
        "medium": (2000, 10000),
        "large": (10000, float('inf'))
    }

    CHUNK_CONFIGS = {
        "tiny": {"chunk_size": None, "overlap": 0},
        "small": {"chunk_size": 1000, "overlap": 0},
        "medium": {"chunk_size": 1500, "overlap": 0},
        "large": {"chunk_size": 2000, "overlap": 0},
    }

    def __init__(self,
                 default_chunk_size: int = 1500,
                 default_chunk_overlap: int = 0,
                 enable_dynamic_sizing: bool = True):
        """
        Args:
            default_chunk_size: 기본 청크 크기
            default_chunk_overlap: 기본 청크 중복 (기본값 0 - 오버랩 없음)
            enable_dynamic_sizing: 동적 크기 조정 활성화
        """
        self.default_chunk_size = default_chunk_size
        self.default_chunk_overlap = default_chunk_overlap
        self.enable_dynamic_sizing = enable_dynamic_sizing

    def chunk_file(self,
                   file_obj: GithubFileObject,
                   repo_id: int) -> List[CodeChunk]:
        """
        파일을 받아서 의미 단위로 자르고, Context를 주입하여 반환합니다.

        Args:
            file_obj: GitHub 파일 객체
            repo_id: 저장소 ID

        Returns:
            CodeChunk 리스트
        """
        try:
            # 1. 빈 파일 필터링
            if not file_obj.content or len(file_obj.content.strip()) == 0:
                logger.debug(f"Skipping empty file: {file_obj.file_path}")
                return []

            # 2. Java 메서드 단위 청킹 시도
            if JavaMethodChunker.should_use_method_chunking(file_obj.content, file_obj.language):
                return self._chunk_java_methods(file_obj, repo_id)

            # 3. 일반 언어 청킹
            return self._chunk_with_langchain_splitter(file_obj, repo_id)

        except Exception as e:
            logger.error(f"Failed to chunk file {file_obj.file_path}: {str(e)}")
            # 실패 시 원본을 단일 청크로 반환
            return self._create_single_chunk(file_obj, repo_id, 0)

    def _chunk_java_methods(self, file_obj: GithubFileObject, repo_id: int) -> List[CodeChunk]:
        """Java 파일을 메서드 단위로 청킹"""
        logger.debug(f"Using Java method-level chunking for: {file_obj.file_path}")
        raw_texts = JavaMethodChunker.chunk_java_file(file_obj.content)

        if len(raw_texts) <= 1:
            return self._create_single_chunk(file_obj, repo_id, 0)

        chunks = [
            self._create_chunk_from_text(
                file_obj, repo_id, i, text
            ) for i, text in enumerate(raw_texts)
        ]
        logger.info(f"Java method chunking: {file_obj.file_path} -> {len(chunks)} chunks")
        return chunks

    def _chunk_with_langchain_splitter(self, file_obj: GithubFileObject, repo_id: int) -> List[CodeChunk]:
        """LangChain의 RecursiveCharacterTextSplitter를 사용하여 파일을 청킹"""
        chunk_size, chunk_overlap = self._get_chunk_config(file_obj.content)

        if chunk_size is None:
            logger.debug(f"File too small to chunk: {file_obj.file_path} ({len(file_obj.content)} chars)")
            return self._create_single_chunk(file_obj, repo_id, 0)

        lang_enum = self._map_language(file_obj.language)
        splitter = RecursiveCharacterTextSplitter.from_language(
            language=lang_enum, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        ) if lang_enum else RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        logger.debug(f"Using {'language-specific' if lang_enum else 'default'} splitter for {file_obj.language}: {file_obj.file_path}")

        raw_texts = splitter.split_text(file_obj.content)

        if len(raw_texts) == 1 and len(raw_texts[0]) < chunk_size * 1.2:
            logger.debug(f"Single chunk created: {file_obj.file_path}")
            return self._create_single_chunk(file_obj, repo_id, 0)

        chunks = [
            self._create_chunk_from_text(
                file_obj, repo_id, i, text
            ) for i, text in enumerate(raw_texts)
        ]
        logger.info(f"Chunked {file_obj.file_path}: {len(chunks)} chunks created")
        return chunks

    def _get_chunk_config(self, content: str) -> tuple[Optional[int], int]:
        """파일 크기에 따라 동적으로 청크 설정 반환"""
        if not self.enable_dynamic_sizing:
            return self.default_chunk_size, self.default_chunk_overlap

        content_length = len(content)
        for size_category, (min_size, max_size) in self.SIZE_THRESHOLDS.items():
            if min_size <= content_length < max_size:
                config = self.CHUNK_CONFIGS[size_category]
                return config["chunk_size"], config["overlap"]
        return self.default_chunk_size, self.default_chunk_overlap

    def _create_single_chunk(self, file_obj: GithubFileObject, repo_id: int, chunk_index: int) -> List[CodeChunk]:
        """단일 청크 생성 (분할하지 않음)"""
        chunk = self._create_chunk_from_text(
            file_obj, repo_id, chunk_index, file_obj.content
        )
        return [chunk]

    def _create_chunk_from_text(self, file_obj: GithubFileObject, repo_id: int, chunk_index: int, text: str) -> CodeChunk:
        """주어진 텍스트로 CodeChunk 객체를 생성하는 헬퍼 메서드"""
        context_info = self._extract_context_info(text, file_obj.language)
        metadata = self._build_metadata(context_info)
        final_content = f"File: {file_obj.file_path}\n\n{text}"
        chunk_id = f"repo_{repo_id}_{file_obj.file_path}_{chunk_index}"

        return CodeChunk(
            chunk_id=chunk_id,
            file_path=file_obj.file_path,
            content=final_content,
            language=file_obj.language,
            metadata=metadata
        )

    def _build_metadata(self, context_info: dict) -> dict:
        """Metadata 딕셔너리 생성"""
        metadata = {}
        if context_info.get("class_name"):
            metadata["class_name"] = context_info["class_name"]
        if context_info.get("function_name"):
            metadata["function_name"] = context_info["function_name"]
        return metadata

    def _extract_context_info(self, text: str, language: str) -> dict:
        """텍스트에서 함수/클래스명 추출 (정규표현식 기반)"""
        context = {"class_name": None, "function_name": None}
        try:
            # (기존 로직과 동일)
            if language == "python":
                class_match = re.search(r'^class\s+(\w+)', text, re.MULTILINE)
                func_match = re.search(r'^(?:async\s+)?def\s+(\w+)', text, re.MULTILINE)
                if class_match: context["class_name"] = class_match.group(1)
                if func_match: context["function_name"] = func_match.group(1)
            elif language in ["javascript", "typescript"]:
                class_match = re.search(r'^(?:export\s+)?class\s+(\w+)', text, re.MULTILINE)
                func_match = re.search(r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)', text, re.MULTILINE)
                if class_match: context["class_name"] = class_match.group(1)
                if func_match: context["function_name"] = func_match.group(1)
            elif language in ["java", "kotlin", "c_sharp"]:
                class_match = re.search(r'^(?:public\s+|private\s+|protected\s+)?(?:abstract\s+|final\s+|static\s+)?(?:class|interface|enum)\s+(\w+)', text, re.MULTILINE)
                func_match = re.search(r'^\s*(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?(?:[\w<>\[\],\s]+\s+)?(\w+)\s*\(', text, re.MULTILINE)
                if class_match: context["class_name"] = class_match.group(1)
                if func_match:
                    method_name = func_match.group(1)
                    java_keywords = {'return', 'if', 'else', 'for', 'while', 'switch', 'case', 'try', 'catch', 'finally', 'throw', 'new'}
                    if method_name not in java_keywords:
                        context["function_name"] = method_name
            elif language == "go":
                func_match = re.search(r'^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)', text, re.MULTILINE)
                if func_match: context["function_name"] = func_match.group(1)
            elif language == "rust":
                func_match = re.search(r'^(?:pub\s+)?fn\s+(\w+)', text, re.MULTILINE)
                struct_match = re.search(r'^(?:pub\s+)?struct\s+(\w+)', text, re.MULTILINE)
                if struct_match: context["class_name"] = struct_match.group(1)
                if func_match: context["function_name"] = func_match.group(1)
            elif language in ["c", "cpp"]:
                class_match = re.search(r'^(?:class|struct)\s+(\w+)', text, re.MULTILINE)
                func_match = re.search(r'^(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*\{', text, re.MULTILINE)
                if class_match: context["class_name"] = class_match.group(1)
                if func_match: context["function_name"] = func_match.group(1)
        except Exception as e:
            logger.debug(f"Failed to extract context info: {e}")
        return context

    def _map_language(self, lang_str: str) -> Optional[Language]:
        """문자열 언어명을 LangChain Language Enum으로 변환"""
        return self.LANGUAGE_MAP.get(lang_str.lower())

    def get_supported_languages(self) -> List[str]:
        """지원하는 언어 목록 반환"""
        return list(self.LANGUAGE_MAP.keys())

    def get_chunk_stats(self) -> dict:
        """청크 설정 정보 반환 (디버깅/모니터링용)"""
        return {
            "supported_languages": len(self.LANGUAGE_MAP),
            "language_list": self.get_supported_languages(),
            "default_chunk_size": self.default_chunk_size,
            "default_chunk_overlap": self.default_chunk_overlap,
            "dynamic_sizing_enabled": self.enable_dynamic_sizing,
            "size_thresholds": self.SIZE_THRESHOLDS,
            "chunk_configs": self.CHUNK_CONFIGS,
        }
