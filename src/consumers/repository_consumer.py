from faststream.rabbit import RabbitRouter
from src.models.github import GithubRepoSyncRequest
from src.models.search import GithubCodeDocument
from src.services.github_client_adaptive import GithubClientAdaptive  # Adaptive 방식 사용
from src.chunking.code_chunker import CodeChunker
from src.embedding.openai_embedder import OpenAIEmbedder
from src.indexing.meili_indexer import MeiliIndexer
from src.config.settings import get_settings
import logging

router = RabbitRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# 서비스 인스턴스들 초기화 (싱글톤처럼 재사용)
chunker = CodeChunker()
embedder = OpenAIEmbedder()


@router.subscriber("github_repository_queue")
async def sync_repository_code(msg: GithubRepoSyncRequest):
    logger.info(f"🔄 Processing: {msg.owner}/{msg.repo_name} (Branch: {msg.branch})")

    try:
        # 저장소별 인덱스 이름 생성
        index_name = MeiliIndexer.get_index_name(msg.repo_name, msg.branch)
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
        BATCH_SIZE = 20  # 임베딩/인덱싱을 한 번에 처리할 문서 수
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
                    id=GithubCodeDocument.generate_id(msg.repository_id, chunk.file_path, i),
                    file_path=chunk.file_path,
                    category="CODE",
                    source=f"{msg.repo_name}@{msg.branch}",
                    text=chunk.content,
                    repository_id=msg.repository_id,
                    owner=msg.owner,
                    language=chunk.language,
                    html_url=f"https://github.com/{msg.owner}/{msg.repo_name}/blob/{msg.branch}/{chunk.file_path}",
                    metadata=chunk.metadata,  # metadata 전달
                    _vectors={}
                )
                doc_buffer.append(doc)

            # 3. 버퍼가 차면 배치 처리 (Embedding -> Indexing)
            if len(doc_buffer) >= BATCH_SIZE:
                await process_batch(doc_buffer, indexer)
                total_processed += len(doc_buffer)
                doc_buffer = []  # 버퍼 초기화

        # 4. 남은 버퍼 처리
        if doc_buffer:
            await process_batch(doc_buffer, indexer)
            total_processed += len(doc_buffer)

        logger.info(f"Sync Complete | Index: {index_name}, Total Documents: {total_processed}")

    except Exception as e:
        logger.error(f"Failed to sync repository: {e}")
        # Adaptive Client는 자동으로 폴백하므로 별도 처리 불필요


async def process_batch(docs: list[GithubCodeDocument], indexer: MeiliIndexer):
    """
    문서 배치를 임베딩하고 인덱싱합니다.

    Args:
        docs: 처리할 문서 리스트
        indexer: 사용할 MeiliIndexer 인스턴스
    """
    texts = [d.text for d in docs]
    embeddings = await embedder.embed_documents(texts)

    ready_docs = []
    for doc, vector in zip(docs, embeddings):
        # 벡터를 "default" 키를 가진 딕셔너리로 감쌉니다
        doc.vectors = {"default": vector}
        ready_docs.append(doc.model_dump(by_alias=True))

    await indexer.add_documents(ready_docs)