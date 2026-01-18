from faststream.rabbit import RabbitRouter
from src.models.github import GithubRepoSyncRequest
from src.models.search import GithubCodeDocument
from src.services.github_client_adaptive import GithubClientAdaptive  # Adaptive 방식 사용
from src.chunking.code_chunker import CodeChunker
from src.indexing.meili_indexer import MeiliIndexer
from src.config.settings import get_settings
from src.utils.file_utils import get_file_category
import logging

router = RabbitRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# 서비스 인스턴스들 초기화 (싱글톤처럼 재사용)
chunker = CodeChunker()


@router.subscriber("github_repository_queue")
async def sync_repository_code(msg: GithubRepoSyncRequest):
    logger.info(f"🔄 Processing: {msg.owner}/{msg.repo_name} (Branch: {msg.branch})")

    try:
        # 저장소별 인덱스 이름 생성
        index_name = MeiliIndexer.get_index_name(msg.repo_name, msg.branch) + "_code"
        logger.info(f"Using index: {index_name}")

        # 저장소별 Indexer 생성
        indexer = MeiliIndexer(index_name=index_name)

        # Adaptive Client: ZIP 크기에 따라 자동으로 Hybrid 또는 Tree API 선택
        client = GithubClientAdaptive(
            token=msg.github_token,
            max_zip_size_mb=settings.MAX_ZIP_SIZE_MB
        )

        # 배치 처리를 위한 버퍼
        doc_buffer = []
        BATCH_SIZE = 100
        total_processed = 0

        async for file_obj in client.fetch_repo_files(
            msg.owner,
            msg.repo_name,
            msg.branch
        ):
            # 1. Chunking
            chunks = chunker.chunk_file(
                file_obj,
                msg.repository_id
            )

            for i, chunk in enumerate(chunks):
                # 2. Document 변환 (metadata 포함)
                doc = GithubCodeDocument(
                    # Meta
                    source_type = 0,
                    # Primary Key
                    id = GithubCodeDocument.generate_id(chunk.file_path, i),
                    # Repository 정보
                    owner = msg.owner,
                    repo = msg.repo_name,
                    branch = msg.branch,
                    # File 정보
                    file_path = chunk.file_path,
                    chunk_number = i,
                    category = get_file_category(chunk.file_path, chunk.language),
                    # Content
                    text = chunk.content,
                    metadata = chunk.metadata,
                    # Link
                    html_url = f"https://github.com/{msg.owner}/{msg.repo_name}/blob/{msg.branch}/{chunk.file_path}"
                )
                doc_buffer.append(doc)

            # 3. 버퍼가 차면 배치 인덱싱
            if len(doc_buffer) >= BATCH_SIZE:
                ready_docs = [doc.model_dump(by_alias=True) for doc in doc_buffer]
                await indexer.add_documents(ready_docs)
                total_processed += len(doc_buffer)
                doc_buffer = []  # 버퍼 초기화

        # 4. 남은 버퍼 처리
        if doc_buffer:
            ready_docs = [doc.model_dump(by_alias=True) for doc in doc_buffer]
            await indexer.add_documents(ready_docs)
            total_processed += len(doc_buffer)

        logger.info(f"Sync Complete | Index: {index_name}, Total Documents: {total_processed}")

    except Exception as e:
        logger.error(f"Failed to sync repository: {e}")