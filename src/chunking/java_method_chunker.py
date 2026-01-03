"""
Java 메서드 단위 청킹 모듈

구조:
1. 첫 번째 청크: import 문 + 클래스 선언부 (필드 포함)
2. 이후 청크: 각 메서드별로 분리
"""
import re
from typing import List
import logging

logger = logging.getLogger(__name__)


class JavaMethodChunker:
    """Java 파일을 메서드 단위로 청킹"""

    @staticmethod
    def chunk_java_file(content: str) -> List[str]:
        """
        Java 파일을 메서드 단위로 분할

        Returns:
            청크 리스트 (첫 청크는 import + 클래스 선언, 이후는 메서드별)
        """
        try:
            chunks = []

            # 1. import 문과 package 문 찾기
            header_end = JavaMethodChunker._find_class_start(content)

            if header_end == -1:
                # 클래스 선언을 찾지 못하면 전체를 단일 청크로 반환
                logger.debug("No class declaration found, returning as single chunk")
                return [content]

            # 2. 클래스 선언부 찾기
            class_header_end = JavaMethodChunker._find_first_method_start(content, header_end)

            if class_header_end == -1:
                # 메서드가 없으면 전체를 단일 청크로 반환
                logger.debug("No methods found, returning as single chunk")
                return [content]

            # 3. 첫 번째 청크: import + 클래스 선언 + 필드
            first_chunk = content[:class_header_end].rstrip()
            chunks.append(first_chunk)

            # 4. 메서드들 추출
            methods = JavaMethodChunker._extract_methods(content[class_header_end:])

            # 5. 각 메서드를 별도 청크로 추가
            for method in methods:
                if method.strip():
                    chunks.append(method)

            logger.debug(f"Java file chunked into {len(chunks)} chunks (1 header + {len(methods)} methods)")
            return chunks if len(chunks) > 1 else [content]

        except Exception as e:
            logger.error(f"Failed to chunk Java file: {e}")
            return [content]  # 실패 시 전체를 단일 청크로 반환

    @staticmethod
    def _find_class_start(content: str) -> int:
        """
        클래스 선언의 시작 위치 찾기

        Returns:
            클래스 선언 시작 위치 (인덱스), 없으면 -1
        """
        # class, interface, enum, record 등을 찾음
        pattern = r'^\s*(public\s+|private\s+|protected\s+)?(abstract\s+|final\s+|static\s+)?(class|interface|enum|record)\s+\w+'

        for match in re.finditer(pattern, content, re.MULTILINE):
            return match.start()

        return -1

    @staticmethod
    def _find_first_method_start(content: str, start_pos: int) -> int:
        """
        첫 번째 메서드의 시작 위치 찾기

        Args:
            content: 전체 코드
            start_pos: 검색 시작 위치 (클래스 선언 이후)

        Returns:
            첫 메서드 시작 위치, 없으면 -1
        """
        # 메서드 시그니처 패턴
        # public/private/protected [static] [final] ReturnType methodName(...)
        pattern = r'^\s*(public|private|protected)\s+(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?[\w<>\[\],\s]+\s+\w+\s*\([^)]*\)\s*(?:throws\s+[\w\s,]+)?\s*\{'

        search_content = content[start_pos:]
        match = re.search(pattern, search_content, re.MULTILINE)

        if match:
            return start_pos + match.start()

        return -1

    @staticmethod
    def _extract_methods(content: str) -> List[str]:
        """
        메서드들을 추출 (중괄호 매칭 사용)
        메서드 앞의 주석/공백도 포함

        Args:
            content: 메서드 영역 코드 (첫 메서드 시작부터 끝까지)

        Returns:
            메서드 리스트 (각 메서드 앞의 주석 포함)
        """
        methods = []
        current_pos = 0
        last_method_end = 0  # 이전 메서드의 끝 위치

        while current_pos < len(content):
            # 다음 메서드 시작 찾기
            pattern = r'^\s*(public|private|protected)\s+(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?[\w<>\[\],\s]+\s+\w+\s*\([^)]*\)\s*(?:throws\s+[\w\s,]+)?\s*\{'

            match = re.search(pattern, content[current_pos:], re.MULTILINE)

            if not match:
                break

            method_start = current_pos + match.start()
            brace_start = current_pos + match.end() - 1  # '{' 위치

            # 중괄호 매칭으로 메서드 끝 찾기
            method_end = JavaMethodChunker._find_matching_brace(content, brace_start)

            if method_end == -1:
                # 매칭되는 중괄호를 찾지 못하면 나머지 전체를 하나의 메서드로
                method_with_prefix = content[last_method_end:].rstrip()
                if method_with_prefix.strip():
                    methods.append(method_with_prefix)
                break

            # 메서드 추출: 이전 메서드 끝부터 현재 메서드 끝까지 (주석 포함)
            method_with_prefix = content[last_method_end:method_end + 1].rstrip()
            if method_with_prefix.strip():
                methods.append(method_with_prefix)

            last_method_end = method_end + 1
            current_pos = method_end + 1

        return methods

    @staticmethod
    def _find_matching_brace(content: str, start_pos: int) -> int:
        """
        시작 중괄호에 매칭되는 닫는 중괄호 찾기

        Args:
            content: 전체 코드
            start_pos: '{' 위치

        Returns:
            매칭되는 '}' 위치, 없으면 -1
        """
        if start_pos >= len(content) or content[start_pos] != '{':
            return -1

        brace_count = 1
        pos = start_pos + 1
        in_string = False
        in_char = False
        in_comment = False
        in_multiline_comment = False

        while pos < len(content) and brace_count > 0:
            char = content[pos]
            prev_char = content[pos - 1] if pos > 0 else ''
            next_char = content[pos + 1] if pos < len(content) - 1 else ''

            # 문자열 처리
            if char == '"' and prev_char != '\\' and not in_char and not in_comment and not in_multiline_comment:
                in_string = not in_string

            # 문자 리터럴 처리
            elif char == "'" and prev_char != '\\' and not in_string and not in_comment and not in_multiline_comment:
                in_char = not in_char

            # 주석 처리
            elif char == '/' and next_char == '/' and not in_string and not in_char and not in_multiline_comment:
                in_comment = True

            elif char == '\n' and in_comment:
                in_comment = False

            elif char == '/' and next_char == '*' and not in_string and not in_char:
                in_multiline_comment = True

            elif char == '*' and next_char == '/' and in_multiline_comment:
                in_multiline_comment = False
                pos += 1  # '*/' 둘 다 건너뛰기

            # 중괄호 카운팅 (문자열/주석 밖에서만)
            elif not in_string and not in_char and not in_comment and not in_multiline_comment:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1

            pos += 1

        return pos - 1 if brace_count == 0 else -1

    @staticmethod
    def should_use_method_chunking(content: str, language: str) -> bool:
        """
        메서드 단위 청킹을 사용할지 결정

        Args:
            content: 파일 내용
            language: 프로그래밍 언어

        Returns:
            메서드 청킹 사용 여부

        접근 제어자가 없는 메서드, 생성자, 제네릭 메서드 등 모든 메서드 패턴을 감지하지는 못함 -> 이후 AST Tree-Sitter으로 개선
        """
        if language.lower() != "java":
            return False

        # 클래스가 있고, 메서드가 2개 이상 있을 때만 사용
        has_class = JavaMethodChunker._find_class_start(content) != -1

        if not has_class:
            return False

        # 메서드 개수 확인 (간단한 휴리스틱)
        method_pattern = r'^\s*(public|private|protected)\s+(?:static\s+)?[\w<>\[\],\s]+\s+\w+\s*\('
        method_count = len(re.findall(method_pattern, content, re.MULTILINE))

        return method_count >= 2
