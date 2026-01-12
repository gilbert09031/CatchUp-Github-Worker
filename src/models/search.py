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


class GithubPRDocument(BaseModel):
    """
    GitHub PR의 Meilisearch Document 형식
    """

    # ========================================
    # Primary Identification
    # ========================================
    id: str = Field(
        ...,
        description="Unique document ID. Format: pr_{pr_number}"
    )

    # ========================================
    # PR Core Metadata
    # ========================================
    pr_number: int = Field(
        ...,
        description="Pull Request number"
    )

    title: str = Field(
        ...,
        description="PR title - primary search field"
    )

    state: Literal["open", "closed"] = Field(
        ...,
        description="PR state (merged PRs are 'closed' with merged_at set)"
    )

    author: str = Field(
        ...,
        description="GitHub username of PR creator"
    )

    # ========================================
    # Timestamps (Unix timestamps)
    # ========================================
    created_at: int = Field(
        ...,
        description="PR creation timestamp (Unix)"
    )

    updated_at: int = Field(
        ...,
        description="Last update timestamp (Unix)"
    )

    merged_at: Optional[int] = Field(
        default=None,
        description="Merge timestamp (Unix). None if not merged"
    )

    closed_at: Optional[int] = Field(
        default=None,
        description="Close timestamp (Unix). None if still open"
    )

    # ========================================
    # Rich Content (검색용)
    # ========================================
    body: str = Field(
        default="",
        description="PR description/body text"
    )

    commit_messages: List[str] = Field(
        default_factory=list,
        description="List of commit messages in this PR"
    )

    # ========================================
    # File Changes Information
    # ========================================
    changed_files: List[str] = Field(
        default_factory=list,
        description="List of file paths modified in this PR"
    )

    additions: int = Field(
        default=0,
        description="Total lines added"
    )

    deletions: int = Field(
        default=0,
        description="Total lines deleted"
    )

    changed_files_count: int = Field(
        default=0,
        description="Number of files changed"
    )

    # ========================================
    # Categorization & Labels
    # ========================================
    labels: List[str] = Field(
        default_factory=list,
        description="GitHub labels attached to this PR"
    )

    milestone: Optional[str] = Field(
        default=None,
        description="Milestone name if assigned"
    )

    # ========================================
    # Repository Context
    # ========================================
    repository_id: int = Field(
        ...,
        description="Internal repository ID"
    )

    owner: str = Field(
        ...,
        description="Repository owner"
    )

    repo_name: str = Field(
        ...,
        description="Repository name"
    )

    branch: str = Field(
        ...,
        description="Base branch (e.g., 'main')"
    )

    source: str = Field(
        ...,
        description="Format: {repo_name}@{branch}"
    )

    html_url: str = Field(
        ...,
        description="Direct link to PR on GitHub"
    )

    # ========================================
    # Vector Embedding
    # ========================================
    vectors: Dict[str, List[float]] = Field(
        ...,
        alias="_vectors",
        description="Embedding vectors for semantic search"
    )

    # ========================================
    # Pydantic Configuration
    # ========================================
    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }

    # ========================================
    # Helper Methods
    # ========================================

    @staticmethod
    def generate_id(pr_number: int) -> str:
        """Document ID 생성"""
        return f"pr_{pr_number}"

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

    @classmethod
    def from_github_api(
            cls,
            pr_data: dict,
            repository_id: int,
            owner: str,
            repo_name: str,
            branch: str
    ) -> "GithubPRDocument":
        """GitHub API 응답으로부터 Document 생성"""
        return cls(
            id=cls.generate_id(pr_data["pr_number"]),
            pr_number=pr_data["pr_number"],
            title=pr_data["title"],
            state=pr_data["state"],
            author=pr_data["author"],
            created_at=pr_data["created_at"],
            updated_at=pr_data["updated_at"],
            merged_at=pr_data.get("merged_at"),
            closed_at=pr_data.get("closed_at"),
            body=pr_data.get("body", ""),
            commit_messages=pr_data.get("commit_messages", []),
            changed_files=pr_data.get("changed_files", []),
            additions=pr_data.get("additions", 0),
            deletions=pr_data.get("deletions", 0),
            changed_files_count=pr_data.get("changed_files_count", 0),
            labels=pr_data.get("labels", []),
            milestone=pr_data.get("milestone"),
            repository_id=repository_id,
            owner=owner,
            repo_name=repo_name,
            branch=branch,
            source=f"{repo_name}@{branch}",
            html_url=pr_data["html_url"],
            _vectors={}
        )

    def get_summary(self) -> str:
        """Document 요약 정보 반환"""
        return (
            f"PR #{self.pr_number}: {self.title}\n"
            f"  Author: {self.author}\n"
            f"  State: {self.state}\n"
            f"  Files: {self.changed_files_count} "
            f"(+{self.additions}/-{self.deletions})\n"
            f"  Commits: {len(self.commit_messages)}"
        )