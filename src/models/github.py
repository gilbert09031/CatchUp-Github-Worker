from pydantic import BaseModel, Field
from typing import Optional

# [RabbitMQ 수신용] Spring Boot가 보내는 "동기화 요청" 메시지
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