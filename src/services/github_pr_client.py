import httpx
import logging
from typing import Dict, List, Optional
from datetime import datetime
from urllib.parse import quote

from src.services.github_client_base import GithubClientBase
from src.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# Custom Exceptions
class GithubAPIError(Exception):
    pass


class PRNotFoundError(GithubAPIError):
    pass


class RateLimitError(GithubAPIError):
    pass

# Main Client
class GithubPrClient(GithubClientBase):
    def __init__(self, token: str = None):
        super().__init__(token)

    async def fetch_pr_metadata(
            self,
            owner: str,
            repo: str,
            pr_number: int
    ) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # URL 인코딩
                safe_owner = quote(owner, safe='')
                safe_repo = quote(repo, safe='')

                logger.info(f"Fetching PR metadata: {owner}/{repo}#{pr_number}")

                # 1. PR 기본 정보 수집
                pr_data = await self._fetch_pr_basic_info(
                    client, safe_owner, safe_repo, pr_number
                )

                # 2. 변경된 파일 목록 수집
                files_data = await self._fetch_pr_files(
                    client, safe_owner, safe_repo, pr_number
                )

                # 3. 커밋 메시지 수집
                commits_data = await self._fetch_pr_commits(
                    client, safe_owner, safe_repo, pr_number
                )

                # 4. 통합 반환
                metadata = {
                    "pr_number": pr_number,
                    "title": pr_data["title"],
                    "body": pr_data.get("body") or "",
                    "state": pr_data["state"],
                    "author": pr_data["user"]["login"],
                    "created_at": self._parse_timestamp(pr_data["created_at"]),
                    "updated_at": self._parse_timestamp(pr_data["updated_at"]),
                    "merged_at": self._parse_timestamp(pr_data.get("merged_at")),
                    "closed_at": self._parse_timestamp(pr_data.get("closed_at")),
                    "changed_files": files_data["changed_files"],
                    "additions": files_data["additions"],
                    "deletions": files_data["deletions"],
                    "changed_files_count": files_data["changed_files_count"],
                    "commit_messages": commits_data["commit_messages"],
                    "labels": [label["name"] for label in pr_data.get("labels", [])],
                    "milestone": pr_data.get("milestone", {}).get("title") if pr_data.get("milestone") else None,
                    "html_url": pr_data["html_url"]
                }

                logger.info(
                    f"PR #{pr_number} metadata collected: "
                    f"{files_data['changed_files_count']} files, "
                    f"{len(commits_data['commit_messages'])} commits"
                )

                return metadata

        except httpx.HTTPStatusError as e:
            self._handle_http_error(e, owner, repo, pr_number)

        except httpx.TimeoutException:
            raise GithubAPIError(
                f"Timeout while fetching PR #{pr_number} from {owner}/{repo}"
            )

        except Exception as e:
            raise GithubAPIError(
                f"Unexpected error fetching PR #{pr_number}: {str(e)}"
            )

    async def _fetch_pr_basic_info(
            self,
            client: httpx.AsyncClient,
            owner: str,
            repo: str,
            pr_number: int
    ) -> Dict:
        """
        API: GET /repos/{owner}/{repo}/pulls/{pr_number}
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"

        logger.debug(f"[1/3] Fetching PR basic info: {url}")

        response = await client.get(url, headers=self.headers)
        response.raise_for_status()

        return response.json()

    async def _fetch_pr_files(
            self,
            client: httpx.AsyncClient,
            owner: str,
            repo: str,
            pr_number: int
    ) -> Dict:
        """
        API: GET /repos/{owner}/{repo}/pulls/{pr_number}/files
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"

        logger.debug(f"[2/3] Fetching PR files: {url}")

        response = await client.get(url, headers=self.headers)
        response.raise_for_status()

        files_data = response.json()

        # 파일 경로만 추출
        changed_files = [file["filename"] for file in files_data]

        # 추가/삭제 라인 수 집계
        additions = sum(file.get("additions", 0) for file in files_data)
        deletions = sum(file.get("deletions", 0) for file in files_data)

        return {
            "changed_files": changed_files,
            "additions": additions,
            "deletions": deletions,
            "changed_files_count": len(changed_files)
        }

    async def _fetch_pr_commits(
            self,
            client: httpx.AsyncClient,
            owner: str,
            repo: str,
            pr_number: int
    ) -> Dict:
        """
        API: GET /repos/{owner}/{repo}/pulls/{pr_number}/commits
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/commits"

        logger.debug(f"[3/3] Fetching PR commits: {url}")

        response = await client.get(url, headers=self.headers)
        response.raise_for_status()

        commits_data = response.json()

        # 커밋 메시지만 추출
        commit_messages = [
            commit["commit"]["message"]
            for commit in commits_data
        ]

        return {
            "commit_messages": commit_messages
        }

    @staticmethod
    def _parse_timestamp(timestamp_str: Optional[str]) -> Optional[int]:
        """
        ISO 8601 타임스탬프를 Unix timestamp로 변환
        """
        if not timestamp_str:
            return None

        try:
            # ISO 8601 파싱 (Z를 +00:00으로 변환)
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return None

    def _handle_http_error(
            self,
            error: httpx.HTTPStatusError,
            owner: str,
            repo: str,
            pr_number: int
    ):
        """
        HTTP 에러 처리

        Raises:
            PRNotFoundError: 404 에러
            RateLimitError: 403 Rate Limit 에러
            GithubAPIError: 기타 에러
        """
        status_code = error.response.status_code

        if status_code == 404:
            raise PRNotFoundError(
                f"PR #{pr_number} not found in {owner}/{repo}"
            )

        elif status_code == 403:
            # Rate Limit 체크
            rate_limit_remaining = error.response.headers.get("X-RateLimit-Remaining", "unknown")

            if rate_limit_remaining == "0":
                reset_time = error.response.headers.get("X-RateLimit-Reset", "unknown")
                raise RateLimitError(
                    f"GitHub API rate limit exceeded. Resets at Unix timestamp: {reset_time}"
                )
            else:
                raise GithubAPIError(
                    f"Access forbidden to {owner}/{repo}. Check token permissions."
                )

        elif status_code == 401:
            raise GithubAPIError(
                "GitHub authentication failed. Check your token."
            )

        else:
            raise GithubAPIError(
                f"GitHub API error {status_code}: {error.response.text[:200]}"
            )

    async def test_connection(self) -> bool:
        """
        GitHub API 연결 테스트
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.github.com/user",
                    headers=self.headers
                )
                response.raise_for_status()

                user_data = response.json()
                username = user_data.get("login", "anonymous")

                # Rate Limit 정보
                rate_limit_remaining = response.headers.get("X-RateLimit-Remaining", "?")
                rate_limit_total = response.headers.get("X-RateLimit-Limit", "?")
                rate_limit_reset = response.headers.get("X-RateLimit-Reset", "?")

                logger.info(f"GitHub API connected as: {username}")
                logger.info(
                    f"Rate Limit: {rate_limit_remaining}/{rate_limit_total} "
                    f"(resets at Unix timestamp: {rate_limit_reset})"
                )

                return True

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("GitHub token is invalid or expired")
            else:
                logger.error(f"GitHub API error: {e.response.status_code}")
            return False

        except Exception as e:
            logger.error(f"GitHub API connection failed: {e}")
            return False

    async def get_rate_limit_status(self) -> Dict:
        """
        현재 Rate Limit 상태 조회

        Returns:
            {
                "remaining": 4999,
                "limit": 5000,
                "reset": 1705334400,
                "reset_datetime": "2024-01-15 12:00:00"
            }
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.github.com/rate_limit",
                    headers=self.headers
                )
                response.raise_for_status()

                data = response.json()
                core_limit = data["resources"]["core"]

                reset_timestamp = core_limit["reset"]
                reset_datetime = datetime.fromtimestamp(reset_timestamp).strftime("%Y-%m-%d %H:%M:%S")

                return {
                    "remaining": core_limit["remaining"],
                    "limit": core_limit["limit"],
                    "reset": reset_timestamp,
                    "reset_datetime": reset_datetime
                }

        except Exception as e:
            logger.error(f"Failed to fetch rate limit: {e}")
            return {
                "remaining": "unknown",
                "limit": "unknown",
                "reset": "unknown",
                "reset_datetime": "unknown"
            }