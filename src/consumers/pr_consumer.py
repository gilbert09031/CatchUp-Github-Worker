"""
PR Consumer: PR 메타데이터 수집 및 인덱싱

1. RabbitMQ에서 PR 동기화 요청 수신
2. GitHub API로 메타데이터 수집
3. GithubPRDocument 생성
4. Meilisearch 인덱싱 (임베딩은 Meilisearch가 자동 처리)
"""

import logging
from faststream.rabbit import RabbitRouter

from src.models.github import GithubPRSyncRequest
from src.models.search import GithubPRDocument
from src.services.github_pr_client import (
    GithubPrClient,
    PRNotFoundError,
    RateLimitError,
    GithubAPIError
)
from src.indexing.meili_indexer import MeiliIndexer
from src.config.settings import get_settings

router = RabbitRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# 서비스 인스턴스 초기화 (싱글톤)
pr_client = GithubPrClient()


@router.subscriber("github_pull_request_queue")
async def sync_pr_metadata(msg: GithubPRSyncRequest):
    logger.info(
        f" Processing PR sync request: "
        f"{msg.owner}/{msg.repo_name}#{msg.pr_number}"
    )

    try:
        # 1. 인덱스 이름 생성
        # 형식: {repo_name}_{branch}_pr
        index_name = MeiliIndexer.get_index_name(msg.repo_name, msg.branch) + "_pr"
        logger.info(f"Target index: {index_name}")

        # 2. Indexer 생성
        indexer = MeiliIndexer(index_name=index_name)

        # 3. GitHub API로 PR 메타데이터 수집
        logger.info(f"Fetching PR metadata from GitHub API...")
        pr_data = await pr_client.fetch_pr_metadata(
            owner=msg.owner,
            repo=msg.repo_name,
            pr_number=msg.pr_number
        )

        logger.info(
            f"Metadata collected: {len(pr_data['changed_files'])} files, "
            f"{len(pr_data['commit_messages'])} commits"
        )

        # 4. GithubPRDocument 생성
        logger.info(f"Creating PR document...")
        doc = GithubPRDocument(
            # Meta
            source_type = 1,
            # Primary Key
            pr_number = pr_data["pr_number"],
            # Repository 정보
            owner = msg.owner,
            repo = msg.repo_name,
            base_branch = pr_data['base_branch'],
            head_branch = pr_data['head_branch'],
            # PR 기본 정보
            title = pr_data["title"],
            body = pr_data.get("body", ""),
            state = pr_data["state"],
            author = pr_data["author"],
            # Timestamps
            created_at = pr_data["created_at"],
            updated_at = pr_data["updated_at"],
            merged_at = pr_data.get("merged_at"),
            closed_at = pr_data.get("closed_at"),
            # Commits
            commit_messages = pr_data.get("commit_messages", []),
            # File Changes
            changed_files = pr_data.get("changed_files", []),
            additions = pr_data.get("additions", 0),
            deletions = pr_data.get("deletions", 0),
            # Labels & Milestone
            labels = pr_data.get("labels", []),
            milestone = pr_data.get("milestone"),
            # Link
            html_url = pr_data["html_url"]
        )

        # 5. Meilisearch 인덱싱 (임베딩은 Meilisearch가 자동 처리)
        logger.info(f"Indexing to Meilisearch...")
        doc_dict = doc.model_dump(by_alias=True)
        await indexer.add_documents([doc_dict])

        logger.info(
            f"PR #{msg.pr_number} indexed successfully to '{index_name}'"
        )

        # 6. 요약 로그
        logger.info(
            f"Summary: "
            f"PR #{doc.pr_number} | "
            f"State: {doc.state} | "
            f"Files: {len(doc.changed_files)} | "
            f"Author: {doc.author}"
        )

    except PRNotFoundError as e:
        logger.error(f"PR not found: {e}")
        # 404는 재시도 불필요 - 메시지 소비 완료

    except RateLimitError as e:
        logger.error(f"GitHub Rate Limit exceeded: {e}")
        # Rate Limit은 재시도 필요
        raise

    except GithubAPIError as e:
        logger.error(f" GitHub API error: {e}")
        # API 에러 - 일시적 문제일 수 있으므로 재시도
        raise

    except Exception as e:
        logger.error(f"Failed to sync PR #{msg.pr_number}: {e}")
        logger.exception("Full traceback:")
        # 예상치 못한 에러 - 재시도
        raise