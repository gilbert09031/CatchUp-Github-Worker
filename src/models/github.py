from pydantic import BaseModel, Field
from typing import Optional

# [RabbitMQ 수신용] Repository 동기화 요청 형식 -> CodeBase Indexing
class GithubRepoSyncRequest(BaseModel):
    repository_id: int = Field(..., description="DB PK of the repository")
    owner: str = Field(..., description="Github Owner (userId or OrganizationName)")
    repo_name: str = Field(..., description="Github Repo Name")
    branch: str = Field("main", description="Target branch to sync")
    github_token: Optional[str] = Field(None, description="User's access token if needed")

# GitHub API에서 가져온 파일 정보를 담을 객체
class GithubFileObject(BaseModel):
    file_path: str
    content: str
    language: str
    size: int

# [Rabbit MQ 수신용] PR 동기화 요청 형식 -> PR Indexing
class GithubPRSyncRequest(BaseModel):
    repository_id: int = Field(..., description="Internal repository ID from database")

    owner: str = Field(..., description="GitHub owner (username or organization)")

    repo_name: str = Field(..., description="Repository name")

    branch: str = Field(..., description="Base branch to associate this PR with (e.g., 'main', 'develop')")

    pr_number: int = Field(..., description="Pull Request number to sync")

    github_token: Optional[str] = Field(
        default=None,
        description="Optional user-specific GitHub token for private repos"
    )

# [Rabbit MQ 수신용] Issue 동기화 요청 형식 -> Issue Indexing
class GithubIssueSyncRequest(BaseModel):
    repository_id: int
    owner: str
    repo_name: str
    issue_number: int
    github_token: Optional[str] = None