"""
PR Consumer: PR 메타데이터 수집 및 인덱싱

1. RabbitMQ에서 PR 동기화 요청 수신
2. GitHub API로 메타데이터 수집
3. GithubPRDocument 생성
4. OpenAI Embedding 생성
5. Meilisearch 인덱싱
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
from src.embedding.openai_embedder import OpenAIEmbedder
from src.indexing.meili_indexer import MeiliIndexer
from src.config.settings import get_settings

router = RabbitRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# 서비스 인스턴스 초기화 (싱글톤)
pr_client = GithubPrClient()
embedder = OpenAIEmbedder()


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
            f"Metadata collected: {pr_data['changed_files_count']} files, "
            f"{len(pr_data['commit_messages'])} commits"
        )

        # 4. GithubPRDocument 생성
        logger.info(f"Creating PR document...")
        doc = GithubPRDocument.from_github_api(
            pr_data=pr_data,
            repository_id=msg.repository_id,
            owner=msg.owner,
            repo_name=msg.repo_name,
            branch=msg.branch
        )

        # 5. 검색용 텍스트 생성
        search_text = GithubPRDocument.generate_search_text(
            title=doc.title,
            body=doc.body,
            commit_messages=doc.commit_messages
        )

        logger.info(f"Search text generated: {len(search_text)} characters")

        # 6. Embedding 생성
        logger.info(f"Generating embedding...")
        embedding = await embedder.embed_documents([search_text])
        doc.vectors = {"default": embedding[0]}

        logger.info(f"Embedding generated: {len(embedding[0])} dimensions")

        # 7. Meilisearch 인덱싱
        logger.info(f"Indexing to Meilisearch...")
        doc_dict = doc.model_dump(by_alias=True)
        await indexer.add_documents([doc_dict])

        logger.info(
            f"PR #{msg.pr_number} indexed successfully to '{index_name}'"
        )

        # 8. 요약 로그
        logger.info(
            f"Summary: "
            f"PR #{doc.pr_number} | "
            f"State: {doc.state} | "
            f"Files: {doc.changed_files_count} | "
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