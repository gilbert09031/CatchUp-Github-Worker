"""
하이브리드 GitHub Client: ZIP 다운로드 + 이후 AST 확장을 고려하여 Tree-Sitter 제공 PL만 추출

- ZIP 다운로드를 위한 1회의 API 호출
"""
import httpx
import io
import zipfile
import logging
from typing import AsyncGenerator
from urllib.parse import quote

from src.models.github import GithubFileObject
from src.config.settings import get_settings
from src.services.github_client_base import GithubClientBase

logger = logging.getLogger(__name__)
settings = get_settings()


class GithubClientHybrid(GithubClientBase):
    def __init__(self, token: str = None):
        super().__init__(token)

    async def fetch_repo_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        max_zip_size_mb: int = 500  # 최대 ZIP 크기 제한 (기본 500MB)
    ) -> AsyncGenerator[GithubFileObject, None]:
        """
        ZIP 다운로드 + Tree-Sitter 필터링 하이브리드 방식

        장점:
        - 1번의 API 호출로 전체 저장소 다운로드
        - Tree-Sitter 지원 파일만 필터링
        - 빠른 속도 + 크기 제한으로 메모리 보호

        Args:
            owner: GitHub 소유자
            repo: 저장소명
            branch: 브랜치명
            max_zip_size_mb: 최대 ZIP 크기 제한 (MB 단위)

        Raises:
            ValueError: ZIP 파일이 제한 크기를 초과할 경우
        """
        # URL 안전하게 인코딩
        safe_owner = quote(owner, safe='')
        safe_repo = quote(repo, safe='')
        safe_branch = quote(branch, safe='')
        url = f"https://api.github.com/repos/{safe_owner}/{safe_repo}/zipball/{safe_branch}"
        max_bytes = max_zip_size_mb * 1024 * 1024

        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            logger.info(f"Downloading ZIP from: {url} (max size: {max_zip_size_mb}MB)")

            # HEAD 요청으로 파일 크기 먼저 확인
            try:
                head_response = await client.head(url, headers=self.headers)
                content_length = head_response.headers.get("content-length")

                if content_length:
                    size_bytes = int(content_length)
                    size_mb = size_bytes / 1024 / 1024
                    logger.info(f"ZIP size: {size_mb:.2f} MB")

                    if size_bytes > max_bytes:
                        raise ValueError(
                            f"Repository ZIP too large: {size_mb:.2f}MB exceeds limit of {max_zip_size_mb}MB. "
                            f"Consider using Tree API mode or increasing max_zip_size_mb parameter."
                        )
            except Exception as e:
                logger.warning(f"Could not check ZIP size via HEAD request: {e}")

            # ZIP 다운로드
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()

            zip_size_mb = len(response.content) / 1024 / 1024
            logger.info(f"ZIP downloaded: {len(response.content):,} bytes ({zip_size_mb:.2f} MB)")

            # 다운로드 후 다시 한번 크기 체크
            if len(response.content) > max_bytes:
                raise ValueError(
                    f"Repository ZIP too large: {zip_size_mb:.2f}MB exceeds limit of {max_zip_size_mb}MB"
                )

            # ZIP 파일 메모리 로드
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                filenames = z.namelist()
                logger.info(f"Total files in ZIP: {len(filenames)}")

                processed = 0
                yielded = 0

                for filename in filenames:
                    processed += 1

                    # 디렉토리 제외
                    if filename.endswith("/"):
                        continue

                    # ZIP 최상위 폴더명 제거
                    clean_path = self.clean_zip_path(filename)
                    if not clean_path:  # 루트 폴더 자체
                        continue

                    # Tree-Sitter 지원 파일만 처리
                    if not self.is_tree_sitter_supported(clean_path):
                        continue

                    try:
                        # 파일 내용 읽기 (UTF-8)
                        content_bytes = z.read(filename)
                        content = content_bytes.decode("utf-8")

                        yielded += 1
                        if yielded % 100 == 0:
                            logger.info(f"Yielded {yielded} Tree-Sitter files (processed {processed}/{len(filenames)})")

                        yield GithubFileObject(
                            file_path=clean_path,
                            content=content,
                            language=self.detect_language(clean_path),
                            size=len(content_bytes)
                        )
                    except UnicodeDecodeError:
                        logger.debug(f"Skipped non-UTF8 file: {clean_path}")
                        continue

                logger.info(f"Completed: {yielded} Tree-Sitter files from {len(filenames)} total files")
