#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 6: BloggerPublisher 구현
09_Blogger연동개발계획.md Phase 6 대응.

Phase 1~5에서 만든 조각들(OAuth 토큰 서비스, 스타일 보정기, 고정요소 삽입기)을
실제로 조립해서 Blogger API를 호출하는 핵심 클래스를 추가합니다.

실행 위치: geo 프로젝트 루트 (docker-compose.yml이 있는 폴더)
사용법: python3 phase6_blogger_publisher_patch.py
"""
import os
import sys
import json

def fail(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)

def create_file(path, content, label):
    if os.path.exists(path):
        print(f"SKIP (이미 존재): {label} ({path})")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"OK (신규 생성): {label}")

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

# ---------------------------------------------------------------------------
# 1) app/Models/ArticleDistribution.php : bloggerPostId() 헬퍼 추가
# ---------------------------------------------------------------------------
edit_file(
    "app/Models/ArticleDistribution.php",
    """    public function wordpressPostId(): ?int
    {
        if ($this->remote_id !== null && ctype_digit((string) $this->remote_id)) {
            return (int) $this->remote_id;
        }

        $meta = is_array($this->remote_meta) ? $this->remote_meta : [];
        $postId = $meta['wordpress_post_id'] ?? null;

        return is_numeric($postId) ? (int) $postId : null;
    }""",
    """    public function wordpressPostId(): ?int
    {
        if ($this->remote_id !== null && ctype_digit((string) $this->remote_id)) {
            return (int) $this->remote_id;
        }

        $meta = is_array($this->remote_meta) ? $this->remote_meta : [];
        $postId = $meta['wordpress_post_id'] ?? null;

        return is_numeric($postId) ? (int) $postId : null;
    }

    public function bloggerPostId(): ?string
    {
        if ($this->remote_id !== null && (string) $this->remote_id !== '') {
            return (string) $this->remote_id;
        }

        $meta = is_array($this->remote_meta) ? $this->remote_meta : [];
        $postId = $meta['blogger_post_id'] ?? null;

        return is_string($postId) && $postId !== '' ? $postId : null;
    }""",
    "ArticleDistribution.php - bloggerPostId() 헬퍼 추가",
)

# ---------------------------------------------------------------------------
# 2) app/Services/GeoFlow/BloggerPublisher.php (신규 파일)
# ---------------------------------------------------------------------------
PUBLISHER_CONTENT = json.loads('"<?php\\n\\nnamespace App\\\\Services\\\\GeoFlow;\\n\\nuse App\\\\Models\\\\ArticleDistribution;\\nuse App\\\\Models\\\\DistributionChannel;\\nuse Illuminate\\\\Http\\\\Client\\\\Response;\\nuse Illuminate\\\\Support\\\\Facades\\\\Http;\\nuse RuntimeException;\\n\\n/**\\n * Blogger API v3 \\ubc1c\\ud589 \\uc5b4\\ub311\\ud130.\\n *\\n * 09_Blogger\\uc5f0\\ub3d9\\uac1c\\ubc1c\\uacc4\\ud68d.md Phase 6 \\ub300\\uc751.\\n * WordPressRestPublisher\\uc640 \\ub3d9\\uc77c\\ud55c \\uacc4\\uc57d(DistributionPublisherInterface)\\uc744 \\ub530\\ub974\\uba70,\\n * Task/Distribution \\ucabd \\uae30\\uc874 \\ucf54\\ub4dc\\ub294 \\uc804\\ud600 \\uc218\\uc815\\ud558\\uc9c0 \\uc54a\\ub294\\ub2e4.\\n *\\n * \\ud30c\\uc774\\ud504\\ub77c\\uc778: OAuth \\ud1a0\\ud070 \\ud655\\ubcf4 -> HTML \\uc2a4\\ud0c0\\uc77c \\ubcf4\\uc815 -> \\uace0\\uc815\\uc694\\uc18c \\uc0bd\\uc785 -> Blogger API \\ud638\\ucd9c\\n */\\nclass BloggerPublisher implements DistributionPublisherInterface\\n{\\n    private const API_BASE = \'https://www.googleapis.com/blogger/v3\';\\n\\n    public function __construct(\\n        private readonly BloggerOAuthTokenService $tokenService,\\n        private readonly BloggerContentStyleAdapter $styleAdapter,\\n        private readonly FixedElementInjector $elementInjector,\\n    ) {}\\n\\n    public function health(DistributionChannel $channel): array\\n    {\\n        $blogId = $this->blogId($channel);\\n        $response = $this->request($channel)->get(self::API_BASE.\'/blogs/\'.$blogId);\\n        $this->throwIfFailed($response, \'Blogger \\uc5f0\\uacb0 \\ud655\\uc778\');\\n\\n        $blog = $response->json();\\n        if (! is_array($blog)) {\\n            $blog = [];\\n        }\\n\\n        return [\\n            \'ok\' => true,\\n            \'channel_type\' => \'blogger\',\\n            \'blog_id\' => $blogId,\\n            \'blog_name\' => (string) ($blog[\'name\'] ?? \'\'),\\n            \'blog_url\' => (string) ($blog[\'url\'] ?? \'\'),\\n        ];\\n    }\\n\\n    public function publish(ArticleDistribution $distribution, array $payload): array\\n    {\\n        $distribution->loadMissing(\'channel\');\\n        $channel = $this->channel($distribution);\\n        $blogId = $this->blogId($channel);\\n\\n        $response = $this->request($channel)\\n            ->post(self::API_BASE.\'/blogs/\'.$blogId.\'/posts\', $this->postPayload($payload));\\n        $this->throwIfFailed($response, \'Blogger \\uae00 \\ubc1c\\ud589\');\\n\\n        return $this->postResult($response);\\n    }\\n\\n    public function update(ArticleDistribution $distribution, array $payload): array\\n    {\\n        $distribution->loadMissing(\'channel\');\\n        $channel = $this->channel($distribution);\\n        $postId = $distribution->bloggerPostId();\\n\\n        if (! $postId) {\\n            return $this->publish($distribution, $payload);\\n        }\\n\\n        $blogId = $this->blogId($channel);\\n\\n        // Blogger API v3 posts.update \\ub294 PUT \\uba54\\uc11c\\ub4dc\\ub97c \\uc0ac\\uc6a9\\ud55c\\ub2e4 (posts.insert \\uc640 \\ub2e4\\ub984\\uc5d0 \\uc8fc\\uc758).\\n        $response = $this->request($channel)\\n            ->put(self::API_BASE.\'/blogs/\'.$blogId.\'/posts/\'.$postId, $this->postPayload($payload));\\n        $this->throwIfFailed($response, \'Blogger \\uae00 \\uc218\\uc815\');\\n\\n        return $this->postResult($response);\\n    }\\n\\n    public function delete(ArticleDistribution $distribution): array\\n    {\\n        $distribution->loadMissing(\'channel\');\\n        $channel = $this->channel($distribution);\\n        $postId = $distribution->bloggerPostId();\\n\\n        if (! $postId) {\\n            return [\\n                \'deleted\' => true,\\n                \'remote_id\' => null,\\n                \'remote_url\' => null,\\n                \'message\' => \'missing_remote_post_id\',\\n            ];\\n        }\\n\\n        $blogId = $this->blogId($channel);\\n        $response = $this->request($channel)\\n            ->delete(self::API_BASE.\'/blogs/\'.$blogId.\'/posts/\'.$postId);\\n        $this->throwIfFailed($response, \'Blogger \\uae00 \\uc0ad\\uc81c\');\\n\\n        return [\\n            \'deleted\' => true,\\n            \'remote_id\' => $postId,\\n            \'remote_url\' => null,\\n        ];\\n    }\\n\\n    /**\\n     * Blogger\\ub294 WordPress\\ucc98\\ub7fc \\uc0ac\\uc774\\ud2b8 \\uc804\\uc5ed \\uc124\\uc815(\\uc81c\\ubaa9/\\uc124\\uba85/\\ud398\\uc774\\uc9c0\\ub2f9 \\uae00 \\uc218)\\uc744 API\\ub85c\\n     * \\ubc14\\uafb8\\ub294 \\uac1c\\ub150\\uc774 \\uc57d\\ud558\\ubbc0\\ub85c, \\ud604\\uc7ac\\ub294 \\uc5f0\\uacb0 \\uc0c1\\ud0dc\\ub9cc \\uc7ac\\ud655\\uc778\\ud558\\ub294 \\ucd5c\\uc18c \\uad6c\\ud604\\uc73c\\ub85c \\ub454\\ub2e4.\\n     */\\n    public function syncSiteSettings(DistributionChannel $channel): array\\n    {\\n        return $this->health($channel);\\n    }\\n\\n    /**\\n     * @param  array<string,mixed>  $payload\\n     * @return array<string,mixed>\\n     */\\n    private function postPayload(array $payload): array\\n    {\\n        $article = is_array($payload[\'article\'] ?? null) ? $payload[\'article\'] : [];\\n        $contentHtml = (string) ($article[\'content_html\'] ?? \'\');\\n\\n        $contentHtml = $this->styleAdapter->adapt($contentHtml);\\n        $contentHtml = $this->elementInjector->inject($contentHtml);\\n\\n        return [\\n            \'title\' => (string) ($article[\'title\'] ?? \'\'),\\n            \'content\' => $contentHtml,\\n        ];\\n    }\\n\\n    private function request(DistributionChannel $channel): \\\\Illuminate\\\\Http\\\\Client\\\\PendingRequest\\n    {\\n        $accessToken = $this->tokenService->getValidAccessToken($channel);\\n\\n        return Http::withToken($accessToken)->timeout(20);\\n    }\\n\\n    private function blogId(DistributionChannel $channel): string\\n    {\\n        $config = $channel->resolvedBloggerConfig();\\n        $blogId = $config[\'blogger_blog_id\'];\\n\\n        if ($blogId === \'\') {\\n            throw new RuntimeException(\'Blogger \\ucc44\\ub110\\uc5d0 blog_id\\uac00 \\uc124\\uc815\\ub418\\uc5b4 \\uc788\\uc9c0 \\uc54a\\uc2b5\\ub2c8\\ub2e4.\');\\n        }\\n\\n        return $blogId;\\n    }\\n\\n    private function channel(ArticleDistribution $distribution): DistributionChannel\\n    {\\n        if (! $distribution->channel instanceof DistributionChannel) {\\n            throw new RuntimeException(\'\\ubc30\\ud3ec \\uae30\\ub85d\\uc5d0 Blogger \\ucc44\\ub110 \\uc815\\ubcf4\\uac00 \\uc5c6\\uc2b5\\ub2c8\\ub2e4.\');\\n        }\\n\\n        return $distribution->channel;\\n    }\\n\\n    private function throwIfFailed(Response $response, string $operation): void\\n    {\\n        if (! $response->failed()) {\\n            return;\\n        }\\n\\n        $body = html_entity_decode(strip_tags((string) $response->body()), ENT_QUOTES | ENT_HTML5, \'UTF-8\');\\n        $body = preg_replace(\'/\\\\s+/\', \' \', trim($body));\\n        $summary = is_string($body) && mb_strlen($body) > 300 ? mb_substr($body, 0, 300).\'...\' : (string) $body;\\n\\n        throw new RuntimeException($operation.\' \\uc2e4\\ud328: HTTP \'.$response->status().($summary !== \'\' ? \' \'.$summary : \'\'));\\n    }\\n\\n    /**\\n     * @return array<string,mixed>\\n     */\\n    private function postResult(Response $response): array\\n    {\\n        $json = $response->json();\\n        if (! is_array($json)) {\\n            throw new RuntimeException(\'Blogger \\uc751\\ub2f5\\uc774 \\uc720\\ud6a8\\ud55c JSON\\uc774 \\uc544\\ub2d9\\ub2c8\\ub2e4.\');\\n        }\\n\\n        $postId = (string) ($json[\'id\'] ?? \'\');\\n\\n        return [\\n            \'remote_id\' => $postId,\\n            \'remote_url\' => (string) ($json[\'url\'] ?? \'\'),\\n            \'remote_meta\' => [\\n                \'blogger_post_id\' => $postId,\\n            ],\\n        ];\\n    }\\n}\\n"')

create_file(
    "app/Services/GeoFlow/BloggerPublisher.php",
    PUBLISHER_CONTENT,
    "BloggerPublisher.php",
)

print("")
print("Phase 6 패치 완료.")
print("다음: docker compose build app && docker compose up -d, 이후 Phase 7(Manager 등록)")