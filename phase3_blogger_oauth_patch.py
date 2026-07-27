#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 3: GEOFlow -> Blogger OAuth 연결 플로우 패치 스크립트
09_Blogger연동개발계획.md Phase 3 대응.

실행 위치: geo 프로젝트 루트 (docker-compose.yml이 있는 폴더)
사용법: python3 phase3_blogger_oauth_patch.py
"""
import sys
import os

def fail(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)

def edit_file(path, old, new, label):
    if not os.path.exists(path):
        fail(f"{label}: 파일이 없습니다 ({path})")
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if old not in src:
        fail(f"{label}: 앵커 문자열을 찾지 못했습니다. 파일이 예상과 다릅니다 ({path})")
    if src.count(old) > 1:
        fail(f"{label}: 앵커 문자열이 2곳 이상에서 발견됐습니다. 수동 확인 필요 ({path})")
    src = src.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"OK: {label}")

def create_file(path, content, label):
    if os.path.exists(path):
        print(f"SKIP (이미 존재): {label} ({path})")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"OK (신규 생성): {label}")

# ---------------------------------------------------------------------------
# 1) config/services.php : blogger OAuth 설정 블록 추가
# ---------------------------------------------------------------------------
edit_file(
    "config/services.php",
    """    'slack' => [
        'notifications' => [
            'bot_user_oauth_token' => env('SLACK_BOT_USER_OAUTH_TOKEN'),
            'channel' => env('SLACK_BOT_USER_DEFAULT_CHANNEL'),
        ],
    ],""",
    """    'slack' => [
        'notifications' => [
            'bot_user_oauth_token' => env('SLACK_BOT_USER_OAUTH_TOKEN'),
            'channel' => env('SLACK_BOT_USER_DEFAULT_CHANNEL'),
        ],
    ],

    'blogger' => [
        'client_id' => env('BLOGGER_OAUTH_CLIENT_ID'),
        'client_secret' => env('BLOGGER_OAUTH_CLIENT_SECRET'),
        'redirect_uri' => env('BLOGGER_OAUTH_REDIRECT_URI'),
        'trust_badge_url' => env('BLOGGER_TRUST_BADGE_URL'),
        'cta_url' => env('BLOGGER_CTA_URL', 'https://web-cadalog-ver10.vercel.app/'),
    ],""",
    "config/services.php - blogger 설정 블록 추가",
)

# ---------------------------------------------------------------------------
# 2) app/Models/DistributionChannel.php : resolvedBloggerConfig() 헬퍼 추가
# ---------------------------------------------------------------------------
edit_file(
    "app/Models/DistributionChannel.php",
    """    /**
     * @return array{
     *   generic_auth_type:string,""",
    """    /**
     * @return array{blogger_blog_id:string}
     */
    public function resolvedBloggerConfig(): array
    {
        $stored = is_array($this->channel_config) ? $this->channel_config : [];

        return [
            'blogger_blog_id' => trim((string) ($stored['blogger_blog_id'] ?? '')),
        ];
    }

    /**
     * @return array{
     *   generic_auth_type:string,""",
    "DistributionChannel.php - resolvedBloggerConfig() 추가",
)

# ---------------------------------------------------------------------------
# 3) routes/web.php : import + connect/callback 라우트 추가
# ---------------------------------------------------------------------------
edit_file(
    "routes/web.php",
    "use App\\Http\\Controllers\\Admin\\DistributionController;",
    "use App\\Http\\Controllers\\Admin\\BloggerOAuthController;\nuse App\\Http\\Controllers\\Admin\\DistributionController;",
    "routes/web.php - BloggerOAuthController import 추가",
)

edit_file(
    "routes/web.php",
    """            Route::get('{channelId}', [DistributionController::class, 'show'])->name('show')->whereNumber('channelId');
            Route::post('{channelId}/health', [DistributionController::class, 'health'])->name('health')->whereNumber('channelId');
        });""",
    """            Route::get('{channelId}', [DistributionController::class, 'show'])->name('show')->whereNumber('channelId');
            Route::post('{channelId}/health', [DistributionController::class, 'health'])->name('health')->whereNumber('channelId');
            Route::get('{channelId}/blogger/connect', [BloggerOAuthController::class, 'redirect'])->name('blogger.connect')->whereNumber('channelId');
            Route::get('blogger/callback', [BloggerOAuthController::class, 'callback'])->name('blogger.callback');
        });""",
    "routes/web.php - blogger connect/callback 라우트 추가",
)

def append_file(path, content, label):
    if not os.path.exists(path):
        fail(f"{label}: 파일이 없습니다 ({path})")
    with open(path, "r", encoding="utf-8") as f:
        existing = f.read()
    if "BLOGGER_OAUTH_CLIENT_ID" in existing:
        print(f"SKIP (이미 추가됨): {label}")
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)
    print(f"OK: {label}")

# ---------------------------------------------------------------------------
# 4) .env.example : Blogger OAuth 변수 안내 추가 (파일 끝에 안전하게 append)
# ---------------------------------------------------------------------------
append_file(
    ".env.example",
    """
# --- Blogger 발행 연동 (GCP OAuth 클라이언트, 09_Blogger연동개발계획.md 참고) ---
BLOGGER_OAUTH_CLIENT_ID=
BLOGGER_OAUTH_CLIENT_SECRET=
BLOGGER_OAUTH_REDIRECT_URI=http://localhost:18080/geo_admin/distribution/blogger/callback
BLOGGER_TRUST_BADGE_URL=
BLOGGER_CTA_URL=https://web-cadalog-ver10.vercel.app/
""",
    ".env.example - Blogger OAuth 변수 추가",
)

# ---------------------------------------------------------------------------
# 5) app/Services/GeoFlow/BloggerOAuthTokenService.php (신규 파일)
# ---------------------------------------------------------------------------
create_file(
    "app/Services/GeoFlow/BloggerOAuthTokenService.php",
    '''<?php

namespace App\\Services\\GeoFlow;

use App\\Models\\DistributionChannel;
use App\\Models\\DistributionChannelSecret;
use App\\Support\\GeoFlow\\ApiKeyCrypto;
use Illuminate\\Support\\Facades\\Http;
use RuntimeException;

/**
 * Blogger API v3 는 사용자(블로그 소유자) 신원으로 발행해야 하므로,
 * 서비스 계정이 아닌 표준 OAuth2 Authorization Code + Refresh Token 방식을 사용한다.
 *
 * 저장 위치:
 * - client_id / client_secret : config('services.blogger') (.env, 앱 단위 1개)
 * - refresh_token             : DistributionChannelSecret (채널별, ApiKeyCrypto로 암호화)
 * - access_token              : 매 호출 시 refresh_token으로 즉시 재발급 (캐시하지 않음, 단순화 우선)
 */
class BloggerOAuthTokenService
{
    public function __construct(
        private readonly ApiKeyCrypto $apiKeyCrypto,
    ) {}

    public function authorizationUrl(string $state): string
    {
        $params = [
            'client_id' => (string) config('services.blogger.client_id'),
            'redirect_uri' => (string) config('services.blogger.redirect_uri'),
            'response_type' => 'code',
            'scope' => 'https://www.googleapis.com/auth/blogger',
            'access_type' => 'offline',
            'prompt' => 'consent',
            'state' => $state,
        ];

        return 'https://accounts.google.com/o/oauth2/v2/auth?'.http_build_query($params);
    }

    /**
     * 인증 코드를 access_token + refresh_token으로 교환한다.
     *
     * @return array{access_token:string, refresh_token:string, expires_in:int}
     */
    public function exchangeCodeForTokens(string $code): array
    {
        $response = Http::asForm()->post('https://oauth2.googleapis.com/token', [
            'code' => $code,
            'client_id' => (string) config('services.blogger.client_id'),
            'client_secret' => (string) config('services.blogger.client_secret'),
            'redirect_uri' => (string) config('services.blogger.redirect_uri'),
            'grant_type' => 'authorization_code',
        ]);

        if ($response->failed()) {
            throw new RuntimeException('Blogger OAuth 코드 교환 실패: '.$response->body());
        }

        $payload = $response->json();
        $refreshToken = (string) ($payload['refresh_token'] ?? '');
        if ($refreshToken === '') {
            throw new RuntimeException('refresh_token이 응답에 없습니다. access_type=offline&prompt=consent 여부를 확인하세요.');
        }

        return [
            'access_token' => (string) ($payload['access_token'] ?? ''),
            'refresh_token' => $refreshToken,
            'expires_in' => (int) ($payload['expires_in'] ?? 3600),
        ];
    }

    /**
     * 채널에 저장된 refresh_token으로 매번 새 access_token을 발급받는다.
     */
    public function getValidAccessToken(DistributionChannel $channel): string
    {
        $secret = DistributionChannelSecret::query()
            ->where('distribution_channel_id', (int) $channel->id)
            ->where('key_id', 'oauth_refresh_token')
            ->where('status', 'active')
            ->first();

        if (! $secret) {
            throw new RuntimeException('Blogger refresh_token이 저장되어 있지 않습니다. 먼저 OAuth 연결을 완료하세요.');
        }

        $refreshToken = $this->apiKeyCrypto->decrypt((string) $secret->secret_ciphertext);
        if ($refreshToken === '') {
            throw new RuntimeException('Blogger refresh_token 복호화에 실패했습니다.');
        }

        $response = Http::asForm()->post('https://oauth2.googleapis.com/token', [
            'client_id' => (string) config('services.blogger.client_id'),
            'client_secret' => (string) config('services.blogger.client_secret'),
            'refresh_token' => $refreshToken,
            'grant_type' => 'refresh_token',
        ]);

        if ($response->failed()) {
            throw new RuntimeException('Blogger access_token 갱신 실패: '.$response->body());
        }

        $accessToken = (string) ($response->json()['access_token'] ?? '');
        if ($accessToken === '') {
            throw new RuntimeException('Blogger access_token 갱신 응답에 토큰이 없습니다.');
        }

        return $accessToken;
    }

    public function storeRefreshToken(DistributionChannel $channel, string $refreshToken): void
    {
        DistributionChannelSecret::query()
            ->where('distribution_channel_id', (int) $channel->id)
            ->where('key_id', 'oauth_refresh_token')
            ->update(['status' => 'revoked']);

        DistributionChannelSecret::query()->create([
            'distribution_channel_id' => (int) $channel->id,
            'key_id' => 'oauth_refresh_token',
            'secret_ciphertext' => $this->apiKeyCrypto->encrypt($refreshToken),
            'status' => 'active',
            'scopes' => ['blogger.publish'],
        ]);
    }
}
''',
    "BloggerOAuthTokenService.php",
)

# ---------------------------------------------------------------------------
# 6) app/Http/Controllers/Admin/BloggerOAuthController.php (신규 파일)
# ---------------------------------------------------------------------------
create_file(
    "app/Http/Controllers/Admin/BloggerOAuthController.php",
    '''<?php

namespace App\\Http\\Controllers\\Admin;

use App\\Http\\Controllers\\Controller;
use App\\Models\\DistributionChannel;
use App\\Services\\GeoFlow\\BloggerOAuthTokenService;
use Illuminate\\Http\\RedirectResponse;
use Illuminate\\Http\\Request;
use Illuminate\\Support\\Str;
use RuntimeException;

/**
 * Blogger 채널 OAuth2 연결 플로우 (Authorization Code + Refresh Token).
 * Apps Script의 ScriptApp.getOAuthToken()과 달리, 서버 앱이므로 표준 OAuth2 절차를 따른다.
 */
class BloggerOAuthController extends Controller
{
    public function __construct(
        private readonly BloggerOAuthTokenService $tokenService,
    ) {}

    public function redirect(Request $request, int $channelId): RedirectResponse
    {
        $channel = DistributionChannel::query()->whereKey($channelId)->first();
        if (! $channel) {
            return redirect()->route('admin.distribution.index')->withErrors(__('admin.distribution.message.not_found'));
        }

        $state = Str::random(32);
        $request->session()->put('blogger_oauth_state', $state);
        $request->session()->put('blogger_oauth_channel_id', $channel->id);

        return redirect()->away($this->tokenService->authorizationUrl($state));
    }

    public function callback(Request $request): RedirectResponse
    {
        $expectedState = (string) $request->session()->pull('blogger_oauth_state', '');
        $channelId = (int) $request->session()->pull('blogger_oauth_channel_id', 0);
        $state = (string) $request->query('state', '');
        $code = (string) $request->query('code', '');

        if ($expectedState === '' || ! hash_equals($expectedState, $state)) {
            return redirect()->route('admin.distribution.index')->withErrors('Blogger OAuth state 값이 일치하지 않습니다. 다시 시도해주세요.');
        }

        $channel = DistributionChannel::query()->whereKey($channelId)->first();
        if (! $channel) {
            return redirect()->route('admin.distribution.index')->withErrors(__('admin.distribution.message.not_found'));
        }

        if ($code === '') {
            return redirect()
                ->route('admin.distribution.show', ['channelId' => (int) $channel->id])
                ->withErrors('Blogger 인증이 취소되었거나 코드가 전달되지 않았습니다.');
        }

        try {
            $tokens = $this->tokenService->exchangeCodeForTokens($code);
            $this->tokenService->storeRefreshToken($channel, $tokens['refresh_token']);
        } catch (RuntimeException $exception) {
            return redirect()
                ->route('admin.distribution.show', ['channelId' => (int) $channel->id])
                ->withErrors('Blogger 연결 실패: '.$exception->getMessage());
        }

        return redirect()
            ->route('admin.distribution.show', ['channelId' => (int) $channel->id])
            ->with('message', 'Blogger 계정이 성공적으로 연결되었습니다.');
    }
}
''',
    "BloggerOAuthController.php",
)

print("")
print("Phase 3 패치 완료.")
print("다음: composer dump-autoload, docker compose build, docker compose up -d, .env에 BLOGGER_OAUTH_CLIENT_ID/SECRET 채우기")