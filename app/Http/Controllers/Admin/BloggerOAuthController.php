<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\DistributionChannel;
use App\Services\GeoFlow\BloggerOAuthTokenService;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
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
