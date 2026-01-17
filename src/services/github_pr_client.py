import httpx
import logging
from typing import Dict, Optional
from datetime import datetime

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

GRAPHQL_PR_QUERY = """
query GetPRMetadata($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number
      title
      body
      state
      author {
        login
      }
      createdAt
      updatedAt
      mergedAt
      closedAt
      headRefName
      baseRefName
      additions
      deletions
      labels(first: 100) {
        nodes {
          name
        }
      }
      milestone {
        title
      }
      url
      files(first: 100) {
        nodes {
          path
          additions
          deletions
        }
      }
      commits(first: 100) {
        nodes {
          commit {
            message
          }
        }
      }
    }
  }
}
"""


class GithubPrClient(GithubClientBase):
    def __init__(self, token: str = None):
        super().__init__(token)
        self.graphql_url = "https://api.github.com/graphql"

    async def fetch_pr_metadata(
            self,
            owner: str,
            repo: str,
            pr_number: int
    ) -> Dict:
        """
        GraphQL로 PR 메타데이터를 한 번에 수집

        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull Request number

        Returns:
            PR 메타데이터 딕셔너리

        Raises:
            PRNotFoundError: PR을 찾을 수 없음
            RateLimitError: Rate Limit 초과
            GithubAPIError: 기타 API 에러
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info(f"Fetching PR metadata via GraphQL: {owner}/{repo}#{pr_number}")

                response = await client.post(
                    self.graphql_url,
                    headers=self.headers,
                    json={
                        "query": GRAPHQL_PR_QUERY,
                        "variables": {
                            "owner": owner,
                            "name": repo,
                            "number": pr_number
                        }
                    }
                )
                response.raise_for_status()

                result = response.json()

                # GraphQL 에러 처리
                if "errors" in result:
                    self._handle_graphql_errors(result["errors"], owner, repo, pr_number)

                # 데이터 추출
                pr_data = result["data"]["repository"]["pullRequest"]

                if pr_data is None:
                    raise PRNotFoundError(
                        f"PR #{pr_number} not found in {owner}/{repo}"
                    )

                # 데이터 변환
                metadata = self._transform_graphql_response(pr_data, pr_number)

                logger.info(
                    f"PR #{pr_number} metadata collected via GraphQL: "
                    f"{len(metadata['changed_files'])} files, "
                    f"{len(metadata['commit_messages'])} commits"
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

    def _transform_graphql_response(self, pr_data: Dict, pr_number: int) -> Dict:
        state = pr_data["state"].lower()

        return {
            "pr_number": pr_number,
            "title": pr_data["title"],
            "body": pr_data.get("body") or "",
            "state": state,
            "author": pr_data["author"]["login"],
            "created_at": self._parse_timestamp(pr_data["createdAt"]),
            "updated_at": self._parse_timestamp(pr_data["updatedAt"]),
            "merged_at": self._parse_timestamp(pr_data.get("mergedAt")),
            "closed_at": self._parse_timestamp(pr_data.get("closedAt")),
            "head_branch": pr_data["headRefName"],
            "base_branch": pr_data["baseRefName"],
            "additions": pr_data["additions"],
            "deletions": pr_data["deletions"],
            "changed_files": [f["path"] for f in pr_data["files"]["nodes"]],
            "commit_messages": [
                c["commit"]["message"]
                for c in pr_data["commits"]["nodes"]
            ],
            "labels": [l["name"] for l in pr_data["labels"]["nodes"]],
            "milestone": (
                pr_data["milestone"]["title"]
                if pr_data.get("milestone")
                else None
            ),
            "html_url": pr_data["url"]
        }

    def _handle_graphql_errors(
            self,
            errors: list,
            owner: str,
            repo: str,
            pr_number: int
    ):
        error_messages = [e.get("message", "") for e in errors]
        combined_error = "; ".join(error_messages)

        # NOT_FOUND 에러 체크
        if any("NOT_FOUND" in e.get("type", "") for e in errors):
            raise PRNotFoundError(
                f"PR #{pr_number} not found in {owner}/{repo}"
            )

        # FORBIDDEN 에러 체크
        if any("FORBIDDEN" in e.get("type", "") for e in errors):
            raise GithubAPIError(
                f"Access forbidden to {owner}/{repo}. Check token permissions."
            )

        # 기타 에러
        raise GithubAPIError(
            f"GraphQL error for PR #{pr_number}: {combined_error}"
        )

    @staticmethod
    def _parse_timestamp(timestamp_str: Optional[str]) -> Optional[int]:
        """
        ISO 8601 타임스탬프를 Unix timestamp로 변환
        """
        if not timestamp_str:
            return None

        try:
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
            rate_limit_remaining = error.response.headers.get(
                "X-RateLimit-Remaining", "unknown"
            )

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