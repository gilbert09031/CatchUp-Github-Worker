from pydantic import BaseModel, Field
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

    file_path: str = Field(..., description="Format: path/to/file.py#0")
    category: str = Field(..., description="'CODE' for programming languages, else file extension with dot (e.g., '.md', '.txt')")
    owner_repo_branch: str = Field(..., description="Format: {owner}_{repo_name}@{branch}")

    text: str = Field(..., description="Chunked content")
    html_url: str = Field(..., description="Direct link to GitHub")

    metadata: Optional[Dict[str, str]] = Field(default=None, description="Additional context metadata (class_name, function_name)")
    vectors: Dict[str, List[float]] = Field(..., alias="_vectors", description="Vector embedding map")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class GithubPRDocument(BaseModel):
    """
    GitHub PR의 Meilisearch Document 형식
    """

    source_type: int = Field(1, description="Source type: 1 for PR")

    # Repository 정보
    owner_repo: str = Field(..., description="Format: {owner}_{repo_name}")
    head_base: str = Field(..., description="Format: {head_branch}->{base_branch}")

    # PR 핵심 정보
    pr_number: int = Field(..., description="Pull Request number")
    title: str = Field(..., description="PR title - primary search field")
    state: Literal["open", "closed", "merged"] = Field(..., description="PR state: 'open', 'closed', or 'merged'")
    author: str = Field(..., description="GitHub username of PR creator")

    # Timestamps (Unix timestamps)
    created_at: int = Field(..., description="PR creation timestamp (Unix)")
    updated_at: int = Field(..., description="Last update timestamp (Unix)")
    merged_at: Optional[int] = Field(default=None, description="Merge timestamp (Unix). None if not merged")
    closed_at: Optional[int] = Field(default=None, description="Close timestamp (Unix). None if still open")

    # Rich Content (검색용)
    body: str = Field(default="", description="PR description/body text")
    commit_messages: List[str] = Field(default_factory=list, description="List of commit messages in this PR")

    # File Changes Information
    changed_files: List[str] = Field(default_factory=list, description="List of file paths modified in this PR")
    additions: int = Field(default=0, description="Total lines added")
    deletions: int = Field(default=0, description="Total lines deleted")

    # Categorization & Labels
    labels: List[str] = Field(default_factory=list, description="GitHub labels attached to this PR")
    milestone: Optional[str] = Field(default=None, description="Milestone name if assigned")

    # Direct Link
    html_url: str = Field(..., description="Direct link to PR on GitHub")

    # Vector Embedding
    vectors: Dict[str, List[float]] = Field(..., alias="_vectors", description="Embedding vectors for semantic search")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }

    @staticmethod
    def generate_search_text(
            title: str,
            body: str,
            commit_messages: List[str]
    ) -> str:
        """
        Embedding을 위한 통합 검색 텍스트 생성

        구조:
        [Title] {title}

        [Body]
        {body}

        [Commits]
        - {commit1}
        - {commit2}
        """
        parts = []

        # Title
        if title:
            parts.append(f"[Title] {title}")

        # Body
        if body and body.strip():
            parts.append(f"[Body]\n{body.strip()}")

        # Commit Messages
        if commit_messages:
            commits_section = "[Commits]\n" + "\n".join(
                f"- {msg.strip()}"
                for msg in commit_messages
                if msg.strip()
            )
            parts.append(commits_section)

        return "\n\n".join(parts)
