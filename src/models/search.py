from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class CodeChunk(BaseModel):
    chunk_id: str = Field(..., description="Unique ID for internal processing (includes chunk_index)")
    file_path: str
    content: str = Field(..., description="Chunked code content with file path header")
    language: str
    embedding: Optional[List[float]] = None

    # Metadata fields (클래스명/함수명 정보만 포함)
    metadata: Optional[Dict[str, str]] = Field(default_factory=dict, description="Additional context metadata (class_name, function_name)")


class GithubCodeDocument(BaseModel):
    id: str = Field(..., description="Unique Document ID (includes chunk index)")

    file_path: str = Field(..., description="Full file path")
    category: str = Field("CODE", description="Category: CODE, COMMIT, PR")
    source: str = Field(..., description="Format: {repo_name}@{branch}")
    text: str = Field(..., description="Chunked content with file path header")

    repository_id: int
    owner: str
    language: str = Field("text", description="Programming language")
    html_url: str = Field(..., description="Direct link to GitHub")

    # Metadata fields (class_name, function_name만 포함)
    metadata: Optional[Dict[str, str]] = Field(default=None, description="Additional context metadata (class_name, function_name)")

    vectors: Dict[str, List[float]] = Field(..., alias="_vectors", description="Vector embedding map")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }

    @classmethod
    def generate_id(cls, repo_id: int, file_path: str, chunk_index: int) -> str:
        """ID 생성 헬퍼 함수"""
        import hashlib
        # 중복 방지를 위한 해시 생성
        unique_str = f"{repo_id}_{file_path}_{chunk_index}"
        hash_suffix = hashlib.md5(unique_str.encode()).hexdigest()[:10]

        safe_name = file_path.split("/")[-1].replace(".", "_")
        # 예: repo_123_main_py_0_a1b2c3d4
        return f"repo_{repo_id}_{safe_name}_{chunk_index}_{hash_suffix}"