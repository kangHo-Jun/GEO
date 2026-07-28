<?php

namespace App\Services\GeoFlow;

use App\Models\ArticleDistribution;
use App\Models\DistributionChannel;
use Illuminate\Http\Client\Response;
use Illuminate\Support\Facades\Http;
use RuntimeException;

/**
 * Blogger API v3 발행 어댑터.
 *
 * 09_Blogger연동개발계획.md Phase 6 대응.
 * WordPressRestPublisher와 동일한 계약(DistributionPublisherInterface)을 따르며,
 * Task/Distribution 쪽 기존 코드는 전혀 수정하지 않는다.
 *
 * 파이프라인: OAuth 토큰 확보 -> HTML 스타일 보정 -> 로컬 이미지 GitHub 재호스팅
 *           -> 고정요소 삽입(뱃지/CTA/서명) -> Blogger API 호출
 *
 * 재호스팅이 고정요소 삽입보다 먼저인 이유: FixedElementInjector가 "본문 이미지가 속한
 * 섹션 끝"을 찾아 뱃지를 배치하는데, 이 시점엔 이미지가 이미 공개 URL이어야
 * 정상적으로 <img> 태그로 인식된다.
 */
class BloggerPublisher implements DistributionPublisherInterface
{
    private const API_BASE = 'https://www.googleapis.com/blogger/v3';

    public function __construct(
        private readonly BloggerOAuthTokenService $tokenService,
        private readonly BloggerContentStyleAdapter $styleAdapter,
        private readonly GitHubImageRehostService $imageRehostService,
        private readonly FixedElementInjector $elementInjector,
    ) {}

    public function health(DistributionChannel $channel): array
    {
        $blogId = $this->blogId($channel);
        $response = $this->request($channel)->get(self::API_BASE.'/blogs/'.$blogId);
        $this->throwIfFailed($response, 'Blogger 연결 확인');

        $blog = $response->json();
        if (! is_array($blog)) {
            $blog = [];
        }

        return [
            'ok' => true,
            'channel_type' => 'blogger',
            'blog_id' => $blogId,
            'blog_name' => (string) ($blog['name'] ?? ''),
            'blog_url' => (string) ($blog['url'] ?? ''),
        ];
    }

    public function publish(ArticleDistribution $distribution, array $payload): array
    {
        $distribution->loadMissing('channel');
        $channel = $this->channel($distribution);
        $blogId = $this->blogId($channel);

        $response = $this->request($channel)
            ->post(self::API_BASE.'/blogs/'.$blogId.'/posts', $this->postPayload($payload));
        $this->throwIfFailed($response, 'Blogger 글 발행');

        return $this->postResult($response);
    }

    public function update(ArticleDistribution $distribution, array $payload): array
    {
        $distribution->loadMissing('channel');
        $channel = $this->channel($distribution);
        $postId = $distribution->bloggerPostId();

        if (! $postId) {
            return $this->publish($distribution, $payload);
        }

        $blogId = $this->blogId($channel);

        // Blogger API v3 posts.update 는 PUT 메서드를 사용한다 (posts.insert 와 다름에 주의).
        $response = $this->request($channel)
            ->put(self::API_BASE.'/blogs/'.$blogId.'/posts/'.$postId, $this->postPayload($payload));
        $this->throwIfFailed($response, 'Blogger 글 수정');

        return $this->postResult($response);
    }

    public function delete(ArticleDistribution $distribution): array
    {
        $distribution->loadMissing('channel');
        $channel = $this->channel($distribution);
        $postId = $distribution->bloggerPostId();

        if (! $postId) {
            return [
                'deleted' => true,
                'remote_id' => null,
                'remote_url' => null,
                'message' => 'missing_remote_post_id',
            ];
        }

        $blogId = $this->blogId($channel);
        $response = $this->request($channel)
            ->delete(self::API_BASE.'/blogs/'.$blogId.'/posts/'.$postId);
        $this->throwIfFailed($response, 'Blogger 글 삭제');

        return [
            'deleted' => true,
            'remote_id' => $postId,
            'remote_url' => null,
        ];
    }

    /**
     * Blogger는 WordPress처럼 사이트 전역 설정(제목/설명/페이지당 글 수)을 API로
     * 바꾸는 개념이 약하므로, 현재는 연결 상태만 재확인하는 최소 구현으로 둔다.
     */
    public function syncSiteSettings(DistributionChannel $channel): array
    {
        return $this->health($channel);
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function postPayload(array $payload): array
    {
        $article = is_array($payload['article'] ?? null) ? $payload['article'] : [];
        $contentHtml = (string) ($article['content_html'] ?? '');

        $contentHtml = $this->styleAdapter->adapt($contentHtml);
        $contentHtml = $this->imageRehostService->rehostLocalImages($contentHtml);
        $contentHtml = $this->elementInjector->inject($contentHtml);

        return [
            'title' => (string) ($article['title'] ?? ''),
            'content' => $contentHtml,
        ];
    }

    private function request(DistributionChannel $channel): \Illuminate\Http\Client\PendingRequest
    {
        $accessToken = $this->tokenService->getValidAccessToken($channel);

        return Http::withToken($accessToken)->timeout(20);
    }

    private function blogId(DistributionChannel $channel): string
    {
        $config = $channel->resolvedBloggerConfig();
        $blogId = $config['blogger_blog_id'];

        if ($blogId === '') {
            throw new RuntimeException('Blogger 채널에 blog_id가 설정되어 있지 않습니다.');
        }

        return $blogId;
    }

    private function channel(ArticleDistribution $distribution): DistributionChannel
    {
        if (! $distribution->channel instanceof DistributionChannel) {
            throw new RuntimeException('배포 기록에 Blogger 채널 정보가 없습니다.');
        }

        return $distribution->channel;
    }

    private function throwIfFailed(Response $response, string $operation): void
    {
        if (! $response->failed()) {
            return;
        }

        $body = html_entity_decode(strip_tags((string) $response->body()), ENT_QUOTES | ENT_HTML5, 'UTF-8');
        $body = preg_replace('/\s+/', ' ', trim($body));
        $summary = is_string($body) && mb_strlen($body) > 300 ? mb_substr($body, 0, 300).'...' : (string) $body;

        throw new RuntimeException($operation.' 실패: HTTP '.$response->status().($summary !== '' ? ' '.$summary : ''));
    }

    /**
     * @return array<string,mixed>
     */
    private function postResult(Response $response): array
    {
        $json = $response->json();
        if (! is_array($json)) {
            throw new RuntimeException('Blogger 응답이 유효한 JSON이 아닙니다.');
        }

        $postId = (string) ($json['id'] ?? '');

        return [
            'remote_id' => $postId,
            'remote_url' => (string) ($json['url'] ?? ''),
            'remote_meta' => [
                'blogger_post_id' => $postId,
            ],
        ];
    }
}
