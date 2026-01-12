import logging
import meilisearch
from typing import List, Dict, Any
from src.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MeiliIndexer:
    def __init__(self, index_name: str = "github_code"):
        self.client = meilisearch.Client(settings.MEILI_URL, settings.MEILI_MASTER_KEY)
        self.index_name = index_name
        self._ensure_index()

    @staticmethod
    def get_index_name(repo_name: str, branch: str) -> str:
        """
        저장소별 인덱스 이름 생성

        Format: {repository_name}_{branch_name}_code
                {repository_name}_{branch_name}_pr
        Args:
            repo_name: 저장소 이름
            branch: 브랜치 이름

        Returns:
            인덱스 이름
        """
        safe_repo = repo_name.replace("-", "_").replace(".", "_")
        safe_branch = branch.replace("/", "_").replace("-", "_")
        return f"{safe_repo}_{safe_branch}"

    def _ensure_index(self):
        try:
            try:
                self.client.create_index(self.index_name, {"primaryKey": "id"})
                logger.info(f"Created new index: {self.index_name}")
            except Exception as e:
                if "already exists" in str(e).lower() or "index_already_exists" in str(e).lower():
                    logger.info(f"Index '{self.index_name}' already exists, using existing index")
                else:
                    raise

            index = self.client.index(self.index_name)

            # 2. 인덱스 타입 판별 (code / pr)
            if "_pr" in self.index_name:
                self._configure_pr_index(index)
            else:
                self._configure_code_index(index)

        except Exception as e:
            logger.error(f"Failed to configure Meilisearch index: {e}")

    def _configure_code_index(self, index):
        "Source Code Index 설정"
        index.update_filterable_attributes([
            "repository_id",
            "owner",
            "language",
            "category",
            "source",
            "metadata.class_name",
            "metadata.function_name"
        ])

        index.update_searchable_attributes([
            "text",
            "file_path",
            "metadata.class_name",
            "metadata.function_name"
        ])

        index.update_sortable_attributes([
            "repository_id"
        ])

        index.update_embedders({
            "default": {
                "source": "userProvided",
                "dimensions": 3072
            }
        })

        logger.info(f" Code index '{self.index_name}' configured")

    def _configure_pr_index(self, index):
        """PR 인덱스 설정"""

        # 1. 필터 가능 속성
        index.update_filterable_attributes([
            # 기본 필터
            "repository_id",
            "owner",
            "repo_name",

            # PR 상태
            "state",  # open, closed
            "author",
            "labels",
            "milestone",

            # 파일 필터
            "changed_files",

            # 시간 범위 필터
            "created_at",
            "updated_at",
            "merged_at",
            "closed_at",

            # 크기 필터
            "changed_files_count",
            "additions",
            "deletions"
        ])

        # 2. 검색 가능 속성
        index.update_searchable_attributes([
            "title",
            "body",
            "commit_messages",
            "changed_files"
        ])

        # 3. 정렬 가능 속성
        index.update_sortable_attributes([
            "created_at",
            "updated_at",
            "merged_at",
            "closed_at",
            "changed_files_count",
            "additions",
            "deletions"
        ])

        # 4. 임베더 설정
        index.update_embedders({
            "default": {
                "source": "userProvided",
                "dimensions": 3072
            }
        })

        logger.info(f" pr index '{self.index_name}' configured")

    async def add_documents(self, documents: List[Dict[str, Any]]):
        if not documents:
            return

        try:
            task = self.client.index(self.index_name).add_documents(documents)
            logger.info(f" Sent {len(documents)} docs to Meilisearch (Task UID: {task.task_uid})")

            result = self.client.wait_for_task(task.task_uid, timeout_in_ms=30000)

            if result.status == "succeeded":
                logger.info(f" Indexing completed: {len(documents)} docs indexed")
            else:
                logger.error(f" Indexing task status: {result.status}")
                if hasattr(result, 'error'):
                    logger.error(f"   Error details: {result.error}")

        except Exception as e:
            logger.error(f" Indexing Failed: {e}")
            raise e