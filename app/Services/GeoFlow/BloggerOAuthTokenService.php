<?php

namespace App\Services\GeoFlow;

use App\Models\DistributionChannel;
use App\Models\DistributionChannelSecret;
use App\Support\GeoFlow\ApiKeyCrypto;
use Illuminate\Support\Facades\Http;
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
