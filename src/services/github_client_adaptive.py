"""
Adaptive GitHub Client: ZIP 크기에 따라 최적의 전략 자동 선택

전략:
1. ZIP File 방식: 빠름, 메모리 사용 높음 → 인스턴스 용량을 고려하여 감당할 수 있으면 선택
2. Tree API 방식: 느림, 메모리 효율적 → 용량이 큰 저장소에 대해서는 압축파일을 메모리에 올리지 않고 하나씩 API 호출
    -> Rate Limit 제한 걸릴 가능성 있음 / 해결 방법 찾아야함
"""
import httpx
import logging
from typing import AsyncGenerator
from urllib.parse import quote

from src.models.github import GithubFileObject
from src.services.github_client import GithubClient
from src.services.github_client_hybrid import GithubClientHybrid
from src.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class GithubClientAdaptive:
    """
    ZIP 크기에 따라 Hybrid 또는 Tree API 방식을 자동 선택하는 어댑터
    """

    def __init__(self, token: str = None, max_zip_size_mb: int = None):
        """
        Args:
            token: GitHub PAT
            max_zip_size_mb: Hybrid 방식 사용 가능한 최대 ZIP 크기 (MB)
                            None이면 settings.MAX_ZIP_SIZE_MB 사용
        """
        self.token = token
        self.max_zip_size_mb = max_zip_size_mb or settings.MAX_ZIP_SIZE_MB
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        api_token = token or getattr(settings, 'GITHUB_TOKEN', None)
        if api_token:
            self.headers["Authorization"] = f"Bearer {api_token}"

    async def fetch_repo_files(
        self,
        owner: str,
        repo: str,
        branch: str
    ) -> AsyncGenerator[GithubFileObject, None]:
        """
        레포지토리 용량을 확인하여 동기화 전략 분기

        전략 선택:
        1. HEAD 요청으로 ZIP 크기 확인
        2. 크기 <= max_zip_size_mb → Hybrid 방식 (빠름, 메모리에 압축파일 로딩)
        3. 크기 > max_zip_size_mb → Tree API 방식 (메모리 효율, 파일마다 API 호출 필요 -> 느림)

        Args:
            owner: GitHub 소유자
            repo: 저장소명
            branch: 브랜치명

        Yields:
            GithubFileObject: 파일 객체
        """
        # URL 안전하게 인코딩
        safe_owner = quote(owner, safe='')
        safe_repo = quote(repo, safe='')
        safe_branch = quote(branch, safe='')
        url = f"https://api.github.com/repos/{safe_owner}/{safe_repo}/zipball/{safe_branch}"

        # 1. HEAD 요청으로 ZIP 크기 확인
        zip_size_mb = await self._check_zip_size(url)

        # 2. 전략 선택
        if zip_size_mb is None:
            # ZIP 크기를 알 수 없는 경우 → 보수적으로 Hybrid 시도
            logger.warning(
                f"Could not determine ZIP size for {owner}/{repo}. "
                f"Attempting Hybrid mode with {self.max_zip_size_mb}MB limit."
            )
            strategy = "hybrid"
        elif zip_size_mb <= self.max_zip_size_mb:
            # ZIP 크기가 제한 이내 → Hybrid 방식 (빠름)
            strategy = "hybrid"
            logger.info(
                f"Using HYBRID mode for {owner}/{repo} "
                f"(ZIP: {zip_size_mb:.2f}MB <= {self.max_zip_size_mb}MB limit)"
            )
        else:
            # ZIP 크기가 제한 초과 → Tree API 방식 (메모리 효율)
            strategy = "tree"
            logger.info(
                f"Using TREE API mode for {owner}/{repo} "
                f"(ZIP: {zip_size_mb:.2f}MB > {self.max_zip_size_mb}MB limit)"
            )

        # 3. 선택된 전략으로 파일 다운로드
        async for file_obj in self._fetch_with_strategy(strategy, owner, repo, branch):
            yield file_obj

    async def _check_zip_size(self, url: str) -> float | None:
        """
        HEAD 요청으로 ZIP 파일 크기 확인

        Args:
            url: ZIP 다운로드 URL

        Returns:
            ZIP 크기 (MB) 또는 None (확인 실패 시)
        """
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                # Body를 제외한 Header만 요청 -> 압축파일 용량 확인용
                head_response = await client.head(url, headers=self.headers)
                content_length = head_response.headers.get("content-length")

                if content_length:
                    size_bytes = int(content_length)
                    size_mb = size_bytes / 1024 / 1024
                    logger.debug(f"ZIP size detected: {size_mb:.2f} MB")
                    return size_mb

        except Exception as e:
            logger.warning(f"Failed to check ZIP size via HEAD request: {e}")

        return None

    async def _fetch_with_strategy(
        self,
        strategy: str,
        owner: str,
        repo: str,
        branch: str
    ) -> AsyncGenerator[GithubFileObject, None]:
        """
        선택된 전략으로 파일 다운로드

        Args:
            strategy: "hybrid" 또는 "tree"
            owner: GitHub 소유자
            repo: 저장소명
            branch: 브랜치명

        Yields:
            GithubFileObject: 파일 객체
        """
        if strategy == "hybrid":
            # Hybrid 방식 (ZIP + Tree-Sitter 필터링)
            client = GithubClientHybrid(token=self.token)
            try:
                async for file_obj in client.fetch_repo_files(
                    owner,
                    repo,
                    branch,
                    max_zip_size_mb=self.max_zip_size_mb
                ):
                    yield file_obj
            except ValueError as e:
                # ZIP 크기 초과 에러 발생 시 Tree API로 폴백
                if "too large" in str(e):
                    logger.warning(
                        f"Hybrid mode failed (ZIP too large), falling back to Tree API mode"
                    )
                    client_tree = GithubClient(token=self.token)
                    async for file_obj in client_tree.fetch_repo_files(owner, repo, branch):
                        yield file_obj
                else:
                    raise

        elif strategy == "tree":
            # Tree API 방식 (개별 파일 다운로드)
            client = GithubClient(token=self.token)
            async for file_obj in client.fetch_repo_files(owner, repo, branch):
                yield file_obj

        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    def get_strategy_info(self) -> dict:
        """
        현재 설정된 전략 정보 반환

        Returns:
            dict: 전략 정보
        """
        return {
            "max_zip_size_mb": self.max_zip_size_mb,
            "hybrid_threshold": f"<= {self.max_zip_size_mb}MB",
            "tree_threshold": f"> {self.max_zip_size_mb}MB",
            "strategy_selection": "automatic based on ZIP size",
        }
