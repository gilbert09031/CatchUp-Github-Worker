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

        Args:
            repo_name: 저장소 이름
            branch: 브랜치 이름

        Returns:
            인덱스 이름
        """
        #  Meilisearch 인덱스 이름 규칙 : 특수문자를 언더스코어로 변환
        safe_repo = repo_name.replace("-", "_").replace(".", "_")
        safe_branch = branch.replace("/", "_").replace("-", "_")
        return f"{safe_repo}_{safe_branch}_code"

    def _ensure_index(self):
        try:
            # 1. 인덱스 생성 (이미 존재하면 무시)
            try:
                self.client.create_index(self.index_name, {"primaryKey": "id"})
                logger.info(f"Created new index: {self.index_name}")
            except Exception as e:
                if "already exists" in str(e).lower() or "index_already_exists" in str(e).lower():
                    logger.info(f"Index '{self.index_name}' already exists, using existing index")
                else:
                    raise

            index = self.client.index(self.index_name)

            # 2. 필터 가능한 속성 설정
            index.update_filterable_attributes([
                "repository_id",
                "owner",
                "language",
                "category",
                "source",
                "metadata.class_name",
                "metadata.function_name"
            ])

            # 3. 검색 가능한 속성 설정
            index.update_searchable_attributes([
                "text",
                "file_path",
                "metadata.class_name",
                "metadata.function_name"
            ])

            # 4. 정렬 가능한 속성 설정
            index.update_sortable_attributes([
                "repository_id"
            ])

            # 5. 임베더 설정 (User Provided - OpenAI)
            index.update_embedders({
                "default": {
                    "source": "userProvided",
                    "dimensions": 1536  # OpenAI text-embedding-3-small dimension
                }
            })

            logger.info(f" Meilisearch Index '{self.index_name}' configured with Embedders and metadata support.")

        except Exception as e:
            logger.error(f" Failed to configure Meilisearch index: {e}")

    async def add_documents(self, documents: List[Dict[str, Any]]):
        if not documents:
            return

        try:
            # add_documents 실행
            task = self.client.index(self.index_name).add_documents(documents)
            logger.info(f" Sent {len(documents)} docs to Meilisearch (Task UID: {task.task_uid})")

            # Task 완료 대기 (타임아웃: 30초)
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