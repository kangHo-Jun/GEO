# 09_Blogger연동개발계획

> 작성일: 2026-07-27
> 대상 저장소: `kangHo-Jun/GEO` (브랜치: `geo-upstream-reference`)
> 목표: GEOFlow가 생성한 글을 Blogger(`daesan-inside.blogspot.com`)에 코드로 직접 발행
> 관련 문서: `08_고정요소가이드.md`(참고용, 채택 안 함), `blogger연결.md`(Apps Script 인증 참고자료)

---

## 0. 왜 이 문서가 필요한가

`blogger연결.md`는 **Google Apps Script** 환경 기준 가이드다. Apps Script는 `ScriptApp.getOAuthToken()`으로 인증 토큰을 자동으로 받지만, GEOFlow는 Docker 위에서 도는 **독립 Laravel 서버**라 이 방식을 그대로 쓸 수 없다.

이 문서는 같은 목적지(Blogger API v3, 같은 블로그)를 향하되, **서버 환경에 맞는 표준 OAuth2 Authorization Code + Refresh Token 방식**으로 다시 설계한 계획이다.

---

## 1. 현황 진단 (코드 확인 완료)

| 확인 항목 | 결과 |
|---|---|
| GEOFlow의 기존 발행 채널 | `geoflow_agent`, `wordpress_rest`, `generic_http_api` 3종 (`DistributionPublisherManager.php`) |
| Blogger 지원 여부 | 없음 (`grep -i blogger` 전체 0건) |
| 발행 인터페이스 계약 | `DistributionPublisherInterface`: `health()`, `publish()`, `update()`, `delete()`, `syncSiteSettings()` 5개 메서드 구현 필수 |
| 참고 가능한 기존 구현체 | `WordPressRestPublisher.php` — 채널 자격증명으로 HTTP 요청 만들고, 응답 실패 시 예외, 결과를 표준 배열로 반환하는 패턴 |
| 자격증명 저장소 | `DistributionChannel` + `DistributionChannelSecret`(암호화된 `secret_ciphertext`) 이미 존재, 재사용 가능 |
| 콘텐츠 형식 | GEOFlow는 Markdown으로 글 생성 → Blogger는 HTML 요구 → 변환기 필요 |
| 고정요소(뱃지/CTA/서명) | 설계만 완료, 미적용 상태 (`WorkerExecutionService.php`에 추가 안 함) — 이번 작업에서 합류 |

**재사용 가능한 실제 값** (`blogger연결.md` 기준)

| 항목 | 값 |
|---|---|
| GCP 프로젝트 | Antigravity, 프로젝트 번호 `122520894478` |
| Blogger API | 이미 활성화됨 (Apps Script에서 확인됨, 프로젝트 공유이므로 재검증만 필요) |
| Blog ID | `3911627335922911456` |
| Blog URL | `https://daesan-inside.blogspot.com/` |
| 필요 OAuth Scope | `https://www.googleapis.com/auth/blogger` |

---

## 2. 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────┐
│  GEOFlow (Laravel, Docker)                                    │
│                                                                 │
│  Task 실행 → 초안(Markdown) 생성 → 검수 승인                    │
│         │                                                       │
│         ▼                                                       │
│  DistributionOrchestrator                                       │
│         │  channel_type = 'blogger' 매칭                        │
│         ▼                                                       │
│  DistributionPublisherManager::forChannel()                     │
│         │  → BloggerPublisher 반환                               │
│         ▼                                                       │
│  BloggerPublisher::publish()                                    │
│    1) BloggerOAuthTokenService → 유효 access_token 확보           │
│    2) MarkdownToBloggerHtmlConverter → HTML 변환                  │
│    3) FixedElementInjector → 뱃지/CTA/서명 삽입                    │
│    4) POST https://www.googleapis.com/blogger/v3/blogs/           │
│       {blogId}/posts                                             │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
              daesan-inside.blogspot.com
```

**핵심 설계 원칙**

1. 기존 `DistributionPublisherInterface` 계약을 그대로 따른다 — Task/Distribution 쪽 코드는 한 줄도 안 건드림
2. OAuth 토큰 발급/갱신 로직은 별도 서비스로 분리한다 — `BloggerPublisher`가 인증 세부사항을 몰라도 되게
3. 마크다운→HTML 변환과 고정요소 삽입은 각각 독립된 클래스로 분리한다 — 나중에 다른 채널(예: 티스토리)에도 재사용 가능하게

---

## 3. 단계별 작업 계획

### Phase 1. GCP OAuth 클라이언트 준비 (사람 작업, 콘솔)

- [ ] GCP Console(Antigravity 프로젝트, `122520894478`) → API 및 서비스 → 사용자 인증 정보
- [ ] **OAuth 클라이언트 ID 생성** — 유형: 웹 애플리케이션
- [ ] 이름: `GEOFlow Blogger Publisher` (하이픈 대신 띄어쓰기 — `blogger연결.md`의 트러블슈팅 항목과 동일한 함정 주의)
- [ ] 승인된 리디렉션 URI 등록:
  - 로컬 테스트: `http://localhost:18080/geo_admin/distributions/blogger/callback`
  - 운영 배포 시 도메인 추가 예정
- [ ] 발급된 `client_id`, `client_secret` 안전하게 보관 (1Password 등, 코드/문서에 절대 하드코딩 금지)
- [ ] OAuth 동의 화면에 테스트 사용자로 본인 Gmail 등록 확인 (Apps Script 설정과 별개로 재확인 필요할 수 있음)

**완료 기준**: `client_id`/`client_secret` 확보, 리디렉션 URI 등록 완료

---

### Phase 2. DB 스키마 보강

**작업 파일**: 신규 마이그레이션 1개

```
database/migrations/2026_07_27_000000_add_blogger_channel_type.php
```

- `distribution_channels.channel_type` 컬럼이 enum/문자열 검증을 쓰는지 확인 후, `'blogger'` 허용값 추가
- 기존 `DistributionChannelSecret` 테이블은 구조 변경 없이 그대로 사용:
  - `key_id = 'oauth_client_id'` → `secret_ciphertext`에 client_id 암호화 저장
  - `key_id = 'oauth_client_secret'` → client_secret 저장
  - `key_id = 'oauth_refresh_token'` → 사용자가 로그인 완료 후 발급받은 refresh_token 저장
- `DistributionChannel`에 `blog_id`(`3911627335922911456`) 저장할 필드 필요 — 기존 채널 설정 JSON 컬럼(있다면) 재사용, 없으면 신규 컬럼 추가

**완료 기준**: `channel_type = 'blogger'`인 채널 1개를 관리자 화면에서 생성 가능

---

### Phase 3. OAuth 연결 플로우 구현

**신규 파일**

```
app/Http/Controllers/Admin/BloggerOAuthController.php
app/Services/GeoFlow/BloggerOAuthTokenService.php
```

**라우트 추가** (`routes/web.php`, `geo_admin` 그룹 내)

```php
Route::get('distributions/blogger/connect', [BloggerOAuthController::class, 'redirect'])->name('distributions.blogger.connect');
Route::get('distributions/blogger/callback', [BloggerOAuthController::class, 'callback'])->name('distributions.blogger.callback');
```

**동작 순서**

1. 관리자가 "Blogger 연결하기" 버튼 클릭 → `redirect()`가 Google OAuth2 동의화면(`https://accounts.google.com/o/oauth2/v2/auth`)으로 리다이렉트
   - `scope=https://www.googleapis.com/auth/blogger`
   - `access_type=offline` (refresh_token 받으려면 필수)
   - `prompt=consent` (재동의 강제, refresh_token 누락 방지)
2. 로그인/동의 완료 → Google이 `callback()`으로 `code` 파라미터와 함께 리다이렉트
3. `callback()`이 `code`를 `https://oauth2.googleapis.com/token`에 POST → `access_token` + `refresh_token` 수신
4. `refresh_token`을 `DistributionChannelSecret`에 암호화 저장
5. 연결 성공 화면 표시

**BloggerOAuthTokenService 핵심 메서드**

```php
class BloggerOAuthTokenService
{
    public function exchangeCodeForTokens(string $code): array;
    public function getValidAccessToken(DistributionChannel $channel): string;
    // 저장된 access_token 만료 여부 확인 → 만료 시 refresh_token으로 재발급 → 캐시
}
```

**완료 기준**: 관리자 화면에서 "Blogger 연결하기" 클릭 → 로그인 → "연결됨" 상태 표시까지 1회 성공

---

### Phase 4. 마크다운 → Blogger HTML 변환기

**신규 파일**

```
app/Services/GeoFlow/MarkdownToBloggerHtmlConverter.php
```

**변환 규칙**

| Markdown 요소 | 변환 결과 |
|---|---|
| `#`, `##`, `###` | `<h1>`, `<h2>`, `<h3>` |
| 표 (`\| ... \|`) | `<table>` (Blogger 테마 호환 위해 인라인 스타일 포함) |
| `**굵게**` | `<strong>` |
| 목록 (`-`, `▶`, `→`) | `<ul><li>` (기호는 텍스트로 유지, 프롬프트 스타일 규칙과 일치) |
| `Q. / A.` FAQ 블록 | `<dl><dt>Q.</dt><dd>A.</dd>` 또는 `<h3>Q.</h3><p>A.</p>` |
| 구분선 `---` | `<hr>` |

**검증 방법**: 변환된 HTML을 로컬에서 렌더링해보고, 표/FAQ가 깨지지 않는지 확인 (headless 브라우저 또는 수동 확인)

**완료 기준**: 이미 생성된 MDF 초안 10개 중 1개를 이 변환기에 통과시켰을 때, 표/FAQ/헤딩이 시각적으로 정상

---

### Phase 5. 고정요소(뱃지·CTA·서명) 삽입기

**신규 파일**

```
app/Services/GeoFlow/FixedElementInjector.php
```

이전에 `WorkerExecutionService.php`에 넣으려다 보류했던 로직을 **독립 클래스로 분리**해서 재작성한다. `WorkerExecutionService.php`(글 생성 단계)가 아니라 **`BloggerPublisher`(발행 직전 단계)**에서만 호출한다 — 이렇게 하면 GEOFlow 로컬 초안에는 고정요소가 안 붙고, 실제 Blogger로 나가는 순간에만 붙는다.

```php
class FixedElementInjector
{
    public function inject(string $html): string
    {
        $html = $this->insertTrustBadge($html, config('services.blogger.trust_badge_url'));
        $html = $this->insertCta($html, 'https://web-cadalog-ver10.vercel.app/');
        $html = $this->appendSignature($html);
        return $html;
    }
    // insertTrustBadge / insertCta / appendSignature: 기존 설계 그대로 (HTML 버전으로 재작성)
}
```

**남은 준비물**: 신뢰뱃지 이미지 URL 확정 (Image Library 업로드 후 확보) — 현재 `TRUST_BADGE_URL_PLACEHOLDER` 상태와 동일하게, `.env`의 `BLOGGER_TRUST_BADGE_URL` 값이 비어있으면 자동 스킵

**완료 기준**: 변환된 HTML에 뱃지 이미지 태그, CTA 버튼, 회사 서명이 지정된 위치에 정확히 1회씩만 삽입됨 (중복 없음)

---

### Phase 6. BloggerPublisher 구현

**신규 파일**

```
app/Services/GeoFlow/BloggerPublisher.php
```

**의존성 주입 구성** (`WordPressRestPublisher` 생성자 패턴과 동일하게)

```php
class BloggerPublisher implements DistributionPublisherInterface
{
    public function __construct(
        private readonly BloggerOAuthTokenService $tokenService,
        private readonly MarkdownToBloggerHtmlConverter $htmlConverter,
        private readonly FixedElementInjector $elementInjector,
    ) {}

    public function health(DistributionChannel $channel): array
    {
        // GET /blogger/v3/blogs/{blogId} — blogger연결.md의 testBloggerAPI()와 동일한 검증
    }

    public function publish(ArticleDistribution $distribution, array $payload): array
    {
        $token = $this->tokenService->getValidAccessToken($channel);
        $html = $this->htmlConverter->convert($payload['content']);
        $html = $this->elementInjector->inject($html);

        // POST /blogger/v3/blogs/{blogId}/posts
        // body: ['title' => $payload['title'], 'content' => $html]
    }

    public function update(...) { /* POST /blogger/v3/blogs/{blogId}/posts/{postId} */ }
    public function delete(...) { /* DELETE /blogger/v3/blogs/{blogId}/posts/{postId} */ }
    public function syncSiteSettings(...) { /* Blogger는 사이트 설정 동기화 개념이 약함 — 최소 구현 또는 no-op */ }
}
```

**완료 기준**: `health()` 호출 시 블로그 정보(이름, URL) 정상 반환

---

### Phase 7. DistributionPublisherManager 등록

**수정 파일**: `app/Services/GeoFlow/DistributionPublisherManager.php`

```php
public function __construct(
    private readonly GeoFlowAgentPublisher $geoFlowAgentPublisher,
    private readonly WordPressRestPublisher $wordPressRestPublisher,
    private readonly GenericHttpApiPublisher $genericHttpApiPublisher,
    private readonly BloggerPublisher $bloggerPublisher,   // 추가
) {}

public function forChannel(DistributionChannel $channel): DistributionPublisherInterface
{
    return match ($channel->channel_type) {
        'geoflow_agent' => $this->geoFlowAgentPublisher,
        'wordpress_rest' => $this->wordPressRestPublisher,
        'generic_http_api' => $this->genericHttpApiPublisher,
        'blogger' => $this->bloggerPublisher,   // 추가
    };
}
```

**완료 기준**: 코드 변경 1줄 매핑 추가로 끝 — 기존 아키텍처가 확장에 열려있음을 확인하는 단계

---

### Phase 8. 통합 테스트

1. Distribution Channel 생성: `channel_type=blogger`, `blog_id=3911627335922911456`, OAuth 연결 완료
2. 테스트 발행: 이미 만들어둔 MDF 초안 10개 중 검수 통과한 것 1개를 이 채널로 발행
3. 확인 항목:
   - [ ] `daesan-inside.blogspot.com`에 실제로 글이 올라갔는가
   - [ ] 제목/본문/표/FAQ가 깨지지 않고 렌더링되는가
   - [ ] 뱃지 이미지, CTA 버튼, 회사 서명이 정확히 1번씩만 있는가
   - [ ] `ArticleDistribution` 레코드에 `remote_id`, `remote_url`이 정상 기록되는가
   - [ ] `update()` 재발행 시 같은 글이 덮어써지는가(중복 글 생성 안 되는지)
4. 9개 나머지 초안도 순차 발행 테스트

**완료 기준**: 10개 초안 전부 Blogger에 정상 발행, 재발행 시 중복 없음

---

## 4. 작업 순서 및 의존관계

```
Phase 1 (GCP 콘솔)
   │
   ▼
Phase 2 (DB 스키마) ──┐
                      ├──▶ Phase 3 (OAuth 플로우)
                      │         │
Phase 4 (MD→HTML) ────┤         │
                      │         ▼
Phase 5 (고정요소) ────┤   Phase 6 (BloggerPublisher, 4/5/OAuth 전부 필요)
                      │         │
                      └─────────▼
                          Phase 7 (Manager 등록)
                                │
                                ▼
                          Phase 8 (통합 테스트)
```

Phase 2, 4, 5는 서로 독립적이라 병렬로 진행 가능. Phase 6은 이 셋이 모두 끝나야 착수 가능.

---

## 5. 리스크 및 롤백 계획

| 리스크 | 대응 |
|---|---|
| refresh_token 발급 실패(`prompt=consent` 누락 시 재로그인해도 refresh_token 안 옴) | Phase 3 구현 시 `access_type=offline&prompt=consent` 반드시 포함, 테스트 시 기존 연결 해제 후 재시도 |
| access_token 만료로 발행 실패 | `getValidAccessToken()`에 만료 5분 전 자동 갱신 로직 포함 |
| HTML 변환 중 표/FAQ 깨짐 | Phase 4 완료 기준에 실제 렌더링 확인 포함, 실패 시 발행 중단(부분 발행 방지) |
| 고정요소 중복 삽입 | `FixedElementInjector`는 `BloggerPublisher`에서만 호출 — `WorkerExecutionService.php`에는 절대 추가하지 않음 (Phase 5 설계 원칙에 명시) |
| GCP OAuth 클라이언트 설정 오류 (`blogger연결.md` 트러블슈팅 사례 재발) | 앱 이름 하이픈 금지, 리디렉션 URI 정확히 일치 확인 |
| 첫 테스트 발행이 실제 공개 블로그에 노출됨 | 테스트 전 Blogger 쪽에서 해당 포스트를 `DRAFT` 상태로 저장하는 옵션 사용 검토 (Blogger API POST 시 `?isDraft=true` 쿼리 파라미터 확인 필요) |

---

## 6. 완료 후 상태

- `향후개발.md`의 "확정 로드맵" 항목이 완료 처리됨
- Task 설정 화면의 Distribution Channel 선택지에 "Blogger" 추가됨
- MDF Task를 포함해 향후 모든 Task가 검수 완료 시 Blogger로 자동 발행 가능
- 이 문서(`09_Blogger연동개발계획.md`)는 완료 후 `완료됨` 상태로 표시하고 저장소에 보관 (다음 채널 확장 시 템플릿으로 재사용)

---

## 7. 다음 확장 후보 (참고, 이번 범위 아님)

- 티스토리, 네이버 블로그 등 추가 채널은 이번에 만든 `MarkdownToBloggerHtmlConverter`/`FixedElementInjector` 패턴을 재사용해 `TistoryPublisher` 등으로 확장 가능
- 이미지 자동 생성 기능(`향후개발.md` 보류 항목 2)이 나중에 추가되면, `FixedElementInjector`가 아니라 `WorkerExecutionService.php` 단계에서 본문 이미지 삽입 — 고정요소(뱃지/CTA)와는 삽입 시점이 다르므로 혼동 주의