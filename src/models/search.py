from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Optional, Literal

class CodeChunk(BaseModel):
    chunk_id: str = Field(..., description="Unique ID for internal processing (includes chunk_index)")
    file_path: str
    content: str = Field(..., description="Chunked code content with file path header")
    language: str
    embedding: Optional[List[float]] = None

    # Metadata fields (클래스명/함수명 정보만 포함)
    metadata: Optional[Dict[str, str]] = Field(default_factory=dict, description="Additional context metadata (class_name, function_name)")


class GithubCodeDocument(BaseModel):
    source_type: int = Field(0, description="Source type: 0 for CODE")

    # Primary Key
    id: str = Field(..., description="Primary Key. UUID5 of filepath + chunk_number")

    # Repository 정보
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")
    branch: str = Field(..., description="Branch name")

    # File 정보
    file_path: str = Field(..., description="Original file path")
    chunk_number: int = Field(..., description="Chunk index")
    category: str = Field(..., description="'CODE' for programming languages, Else file extension ('.md', '.txt')")

    # Content
    text: str = Field(..., description="Chunked content")
    metadata: Optional[Dict[str, str]] = Field(default=None, description="Additional context metadata (class_name, function_name)")

    # Link
    html_url: str = Field(..., description="Direct link to GitHub")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }

    @staticmethod
    def generate_id(file_path: str, chunk_number: int) -> str:
        """Generate deterministic UUID5 from file_path and chunk_number"""
        import uuid
        unique_str = f"{file_path}#{chunk_number}"
        # UUID5: 동일 입력 → 동일 출력, 128비트 공간으로 충돌 방지
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_str))


class GithubPRDocument(BaseModel):
    source_type: int = Field(1, description="Source type: 1 for PR")

    # Primary Key
    pr_number: int = Field(..., description="Primary Key. Pull Request number")

    # Repository 정보
    owner: str = Field(..., description="Repository owner")
    repo: str = Field(..., description="Repository name")
    base_branch: str = Field(..., description="Base branch (target branch)")
    head_branch: str = Field(..., description="Head branch (source branch)")

    # PR 기본 정보
    title: str = Field(..., description="PR title - primary search field")
    body: str = Field(default="", description="PR description/body text")
    state: Literal["open", "closed", "merged"] = Field(..., description="PR state: 'open', 'closed', or 'merged'")
    author: str = Field(..., description="GitHub username of PR creator")

    # Timestamps (Unix timestamps)
    created_at: int = Field(..., description="PR creation timestamp (Unix)")
    updated_at: int = Field(..., description="Last update timestamp (Unix)")
    merged_at: Optional[int] = Field(default=None, description="Merge timestamp (Unix). None if not merged")
    closed_at: Optional[int] = Field(default=None, description="Close timestamp (Unix). None if still open")

    # Commits
    commit_messages: List[str] = Field(default_factory=list, description="List of commit messages in this PR")

    # File Changes
    changed_files: List[str] = Field(default_factory=list, description="List of file paths modified in this PR")
    additions: int = Field(default=0, description="Total lines added")
    deletions: int = Field(default=0, description="Total lines deleted")

    # Labels & Milestone
    labels: List[str] = Field(default_factory=list, description="GitHub labels attached to this PR")
    milestone: Optional[str] = Field(default=None, description="Milestone name if assigned")

    # Link
    html_url: str = Field(..., description="Direct link to PR on GitHub")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }
