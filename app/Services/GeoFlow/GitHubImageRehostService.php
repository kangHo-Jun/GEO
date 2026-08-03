<?php

namespace App\Services\GeoFlow;

use App\Services\Outbound\SafeOutboundHttpClient;
use App\Services\Outbound\SafeOutboundRequest;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Storage;
use RuntimeException;

/**
 * GEOFlow는 localhost(외부 인터넷에서 접근 불가)에서 돌아가므로,
 * Image Library 사진의 상대경로(/storage/...)를 Blogger 본문에 그대로 넣으면
 * 이미지가 깨진다 (Blogger API는 이미지 업로드 엔드포인트 자체를 제공하지 않음).
 *
 * 해결: 발행 직전, 로컬 이미지를 공개 GitHub 저장소에 업로드하고
 * raw.githubusercontent.com 공개 URL로 교체한다 (신뢰뱃지와 동일한 호스팅 방식).
 */
class GitHubImageRehostService
{
    public function __construct(private readonly SafeOutboundHttpClient $safeHttp) {}

    /**
     * HTML 안의 로컬(/storage/...) <img src>를 전부 찾아 GitHub에 업로드하고,
     * 공개 URL로 치환한 HTML을 반환한다.
     */
    public function rehostLocalImages(string $html): string
    {
        $token = trim((string) config('services.github_image_host.token'));
        if ($token === '') {
            // 토큰 미설정 시 원본 그대로 반환 (안전한 폴백, 발행 자체를 막지 않음)
            return $html;
        }

        return preg_replace_callback(
            '/<img\s+([^>]*?)src="(\/storage\/[^"]+)"([^>]*)>/u',
            function (array $matches) use ($token): string {
                [, $before, $localSrc, $after] = $matches;

                try {
                    $publicUrl = $this->uploadLocalImage($localSrc, $token);
                } catch (RuntimeException) {
                    // 업로드 실패 시 원본 태그를 그대로 둔다 (발행 자체는 계속 진행)
                    return $matches[0];
                }

                return '<img '.$before.'src="'.$publicUrl.'"'.$after.'>';
            },
            $html
        ) ?? $html;
    }

    private function uploadLocalImage(string $localSrc, string $token): string
    {
        $diskPath = ltrim((string) preg_replace('#^/storage/#', '', $localSrc), '/');
        if ($diskPath === '' || ! Storage::disk('public')->exists($diskPath)) {
            throw new RuntimeException('로컬 이미지 파일을 찾을 수 없습니다: '.$localSrc);
        }

        $bytes = Storage::disk('public')->get($diskPath);
        $repo = trim((string) config('services.github_image_host.repo'));
        $branch = trim((string) config('services.github_image_host.branch'));
        $pathPrefix = trim((string) config('services.github_image_host.path_prefix'), '/');

        $fileName = date('Ymd_His').'_'.bin2hex(random_bytes(4)).'_'.basename($diskPath);
        $remotePath = $pathPrefix.'/'.$fileName;

        $response = $this->request($token)->put('https://api.github.com/repos/'.$repo.'/contents/'.$remotePath, [
            'message' => 'GEOFlow: Blogger 발행용 이미지 자동 업로드 ('.$fileName.')',
            'content' => base64_encode($bytes),
            'branch' => $branch,
        ]);

        if ($response->failed()) {
            throw new RuntimeException('GitHub 이미지 업로드 실패: '.$response->body());
        }

        return 'https://raw.githubusercontent.com/'.$repo.'/'.$branch.'/'.$remotePath;
    }

    private function request(string $token): SafeOutboundRequest
    {
        $request = Http::withHeaders([
            'Authorization' => 'Bearer '.$token,
            'Accept' => 'application/vnd.github+json',
        ])->timeout(30)
            ->connectTimeout(5)
            ->asJson();

        return new SafeOutboundRequest(
            $this->safeHttp,
            $request,
            (int) config('geoflow.outbound_json_max_bytes', 4 * 1024 * 1024),
        );
    }
}
