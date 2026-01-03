# CatchUp-Github-Worker

GitHub 저장소의 코드를 메서드/함수 단위로 청킹하고, OpenAI 임베딩을 생성하여 Meilisearch에 인덱싱하는 Worker 서비스입니다.

## 주요 기능

### 1. 코드 청킹 
- **25개 언어 지원**: Python, Java, JavaScript, TypeScript, Go, C/C++, Rust, Kotlin 등
- **Java 메서드 단위 청킹**: Java 파일은 메서드 단위로 자동 분할
- **동적 청크 크기 조정**: 파일 크기에 따라 최적의 청크 크기 자동 선택
- **컨텍스트 보존**: 메서드 간 주석 및 공백 유지

### 2. OpenAI 임베딩
- **모델**: text-embedding-3-small (1536 dimensions)
- **배치 처리**: 20개 문서 단위로 배치 임베딩
- **비용 효율적**: 가성비 최적화 모델 사용

### 3. Meilisearch 하이브리드 검색
- **키워드 검색**: 파일 경로, 함수명, 클래스명 검색
- **벡터 검색**: 의미 기반 코드 검색
- **필터링**: 언어, 저장소, 함수명, 클래스명 필터 지원

### 4. 메타데이터 추출 (Metadata Extraction)
- **클래스명**: Java, Python, JavaScript 등의 클래스명 자동 추출
- **함수명**: 메서드, 함수명 정규식 기반 추출
- **언어 감지**: GitHub API 기반 자동 언어 인식

## 아키텍처

```
GitHub Repository
       ↓
GithubClientAdaptive (ZIP 다운로드 또는 파일별 다운로드)
       ↓
CodeChunker (Java 메서드 단위 청킹 / LangChain 기반 청킹)
       ↓
OpenAIEmbedder (text-embedding-3-small)
       ↓
MeiliIndexer (Hybrid Search 지원)
```


### 필드 설명

| 필드 | 설명 |
|------|------|
| `id` | 고유 ID (`repo_{repository_id}_{file_path}_{chunk_index}`) |
| `file_path` | 파일 경로 |
| `category` | 문서 카테고리 (현재: `CODE`) |
| `source` | 저장소@브랜치 형식 |
| `text` | 청킹된 코드 (파일 경로 헤더 포함) |
| `repository_id` | 저장소 ID |
| `owner` | 저장소 소유자 |
| `language` | 프로그래밍 언어 |
| `html_url` | GitHub 소스 코드 URL |
| `metadata.class_name` | 클래스명 (추출된 경우) |
| `metadata.function_name` | 함수/메서드명 (추출된 경우) |
| `_vectors.default` | OpenAI 임베딩 벡터 |


## 주요 컴포넌트

### CodeChunker

**특징**:
- 25개 언어 지원 (LangChain 기반)
- Java는 메서드 단위 자동 청킹
- 파일 크기별 동적 청크 크기 조정
- 함수명, 클래스명 자동 추출

**청크 크기 정책**:
- 500자 이하: 분할 안 함
- 500-2000자: 1000자 청크
- 2000-10000자: 1500자 청크
- 10000자 이상: 2000자 청크

### JavaMethodChunker

**특징**:
- 메서드 단위 정확한 분할
- 메서드 간 주석 보존
- public/private/protected 메서드 지원
- static, final, synchronized 키워드 처리

**청킹 전략**:
1. 첫 번째 청크: import ~ 첫 메서드 직전
2. 이후 청크: 각 메서드 단위 (이전 메서드 끝 ~ 현재 메서드 끝)

### OpenAIEmbedder

**모델**: `text-embedding-3-small`
**차원**: 1536
**배치 크기**: 최대 20개 문서

### MeiliIndexer

**검색 가능 속성**:
- `text` (코드 내용)
- `file_path` (파일 경로)
- `metadata.class_name` (클래스명)
- `metadata.function_name` (함수명)

**필터 가능 속성**:
- `repository_id`
- `owner`
- `language`
- `category`
- `source`
- `metadata.class_name`
- `metadata.function_name`

## 검색 예시

### 키워드 검색

```python
index.search("authentication", {
    "filter": "language = python",
    "limit": 10
})
```

### 하이브리드 검색 (키워드 + 벡터)

```python
# 1. 검색어 임베딩
query_vector = await embedder.embed_documents(["user login authentication"])

# 2. 하이브리드 검색
index.search("login", {
    "vector": query_vector[0],
    "hybrid": {"semanticRatio": 0.7},  # 70% 벡터, 30% 키워드
    "filter": "repository_id = 1",
    "limit": 10
})
```

### 함수명으로 필터링

```python
index.search("", {
    "filter": "metadata.function_name = authenticate",
    "limit": 10
})
```

## 성능 및 최적화

### 메모리 보호
- **ZIP 크기 제한**: 환경별 권장값
  - 1GB (AWS t2.micro): 50MB
  - 2GB (t3.small): 100MB
  - 4GB (t3.medium): 250MB
  - 8GB (t3.large): 500MB

### 배치 처리
- **임베딩 배치**: 20개 문서 단위
- **인덱싱 대기**: Task 완료 대기 (30초 타임아웃)

### GitHub API Rate Limit
- **토큰 없음**: 60 requests/hour
- **토큰 있음**: 5000 requests/hour
- **권장**: GitHub Token 사용

## 향후 개선 사항

- [ ] Tree-Sitter 기반 정확한 AST 파싱
- [ ] 더 많은 언어의 함수/클래스 추출 지원
- [ ] 증분 인덱싱 (변경된 파일만 재처리)
- [ ] 코드 관계 그래프 (함수 호출 관계)
- [ ] 멀티모달 임베딩 (코드 + 문서)