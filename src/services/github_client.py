# src/services/github_client.py
"""
Tree API 방식 GitHub Client: 메모리 효율적, 파일별 다운로드

전략:
- 각 파일을 개별 API 호출로 다운로드
- 메모리 사용량 최소화
- 큰 저장소에 적합
"""
import httpx
import base64
import logging
from typing import AsyncGenerator
from urllib.parse import quote

from src.models.github import GithubFileObject
from src.services.github_client_base import GithubClientBase

logger = logging.getLogger(__name__)


class GithubClient(GithubClientBase):
    """
    GitHub Tree API를 사용한 파일별 다운로드 방식

    특징:
    - 메모리 효율적 (필요한 파일만 다운로드)
    - Tree-Sitter 호환 파일만 필터링
    - 큰 저장소에 적합
    """

    async def fetch_repo_files(
        self,
        owner: str,
        repo: str,
        branch: str
    ) -> AsyncGenerator[GithubFileObject, None]:
        """
        Tree API로 파일 목록을 가져온 후 각 파일을 개별 다운로드

        Args:
            owner: GitHub 소유자
            repo: 저장소명
            branch: 브랜치명

        Yields:
            GithubFileObject: 파일 객체
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 1. Git Tree API로 파일 목록 가져오기
            safe_owner = quote(owner, safe='')
            safe_repo = quote(repo, safe='')
            safe_branch = quote(branch, safe='')
            tree_url = f"https://api.github.com/repos/{safe_owner}/{safe_repo}/git/trees/{safe_branch}?recursive=1"

            logger.info(f"Fetching repository tree from: {tree_url}")

            tree_response = await client.get(tree_url, headers=self.headers)
            tree_response.raise_for_status()
            tree_data = tree_response.json()

            # 2. Tree-Sitter 지원 파일 필터링
            source_files = [
                item for item in tree_data.get("tree", [])
                if item["type"] == "blob" and self.is_tree_sitter_supported(item["path"])
            ]

            logger.info(f"Found {len(source_files)} Tree-Sitter supported files")

            # 3. 각 파일 내용 다운로드
            for idx, file_item in enumerate(source_files, 1):
                file_path = file_item["path"]

                try:
                    # 100개마다 진행 상황 로깅
                    if idx % 100 == 0:
                        logger.info(f"Progress: {idx}/{len(source_files)} files processed")

                    # Blob API로 파일 내용 가져오기
                    blob_url = file_item["url"]
                    blob_response = await client.get(blob_url, headers=self.headers)
                    blob_response.raise_for_status()
                    blob_data = blob_response.json()

                    # Base64 디코딩
                    content_bytes = base64.b64decode(blob_data["content"])
                    content = content_bytes.decode("utf-8")

                    yield GithubFileObject(
                        file_path=file_path,
                        content=content,
                        language=self.detect_language(file_path),
                        size=len(content_bytes)
                    )

                except UnicodeDecodeError:
                    logger.warning(f"Failed to decode file (non UTF-8): {file_path}")
                    continue
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error fetching {file_path}: {e.response.status_code}")
                    continue
                except Exception as e:
                    logger.error(f"Failed to fetch file {file_path}: {str(e)}")
                    continue

            logger.info(f"Completed fetching {len(source_files)} files")
