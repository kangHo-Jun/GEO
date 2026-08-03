<?php

namespace Tests\Unit;

use App\Models\Article;
use App\Models\ArticleDistribution;
use App\Models\Author;
use App\Models\Category;
use App\Models\DistributionChannel;
use App\Models\DistributionChannelSecret;
use App\Services\GeoFlow\BloggerOAuthTokenService;
use App\Services\GeoFlow\BloggerPublisher;
use App\Services\GeoFlow\GitHubImageRehostService;
use App\Support\GeoFlow\ApiKeyCrypto;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Storage;
use Tests\TestCase;

class BloggerServicesTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        config([
            'services.blogger.client_id' => 'blogger-client-id',
            'services.blogger.client_secret' => 'blogger-client-secret',
            'services.blogger.redirect_uri' => 'https://app.example.com/blogger/callback',
            'services.blogger.trust_badge_url' => '',
            'services.blogger.cta_url' => '',
        ]);
    }

    public function test_blogger_health_uses_safe_oauth_and_api_requests(): void
    {
        Http::fake(function (Request $request) {
            if ($request->url() === 'https://oauth2.googleapis.com/token') {
                return Http::response(['access_token' => 'access-token', 'expires_in' => 3600]);
            }

            return Http::response([
                'id' => 'blog-123',
                'name' => 'Daesan Blog',
                'url' => 'https://blog.example.com/',
            ]);
        });

        [$channel] = $this->makeDistribution();
        $result = app(BloggerPublisher::class)->health($channel);

        $this->assertTrue($result['ok']);
        $this->assertSame('blog-123', $result['blog_id']);
        $this->assertSame('Daesan Blog', $result['blog_name']);
        Http::assertSent(fn (Request $request): bool => $request->method() === 'GET'
            && $request->url() === 'https://www.googleapis.com/blogger/v3/blogs/blog-123'
            && $request->hasHeader('Authorization', 'Bearer access-token'));
    }

    public function test_blogger_publish_update_and_delete_keep_their_http_contracts(): void
    {
        Http::fake(function (Request $request) {
            if ($request->url() === 'https://oauth2.googleapis.com/token') {
                return Http::response(['access_token' => 'access-token']);
            }
            if ($request->method() === 'DELETE') {
                return Http::response('', 204);
            }

            return Http::response(['id' => 'post-456', 'url' => 'https://blog.example.com/post-456']);
        });

        [, $distribution] = $this->makeDistribution();
        $publisher = app(BloggerPublisher::class);
        $payload = ['article' => ['title' => 'MDF Guide', 'content_html' => '<p>Body</p>']];

        $published = $publisher->publish($distribution, $payload);
        $distribution->forceFill(['remote_id' => 'post-456'])->save();
        $updated = $publisher->update($distribution->fresh(), $payload);
        $deleted = $publisher->delete($distribution->fresh());

        $this->assertSame('post-456', $published['remote_id']);
        $this->assertSame('post-456', $updated['remote_id']);
        $this->assertTrue($deleted['deleted']);
        Http::assertSent(fn (Request $request): bool => $request->method() === 'POST'
            && $request->url() === 'https://www.googleapis.com/blogger/v3/blogs/blog-123/posts'
            && $request['title'] === 'MDF Guide');
        Http::assertSent(fn (Request $request): bool => $request->method() === 'PUT'
            && $request->url() === 'https://www.googleapis.com/blogger/v3/blogs/blog-123/posts/post-456'
            && str_contains((string) $request['content'], '<p>Body</p>'));
        Http::assertSent(fn (Request $request): bool => $request->method() === 'DELETE'
            && $request->url() === 'https://www.googleapis.com/blogger/v3/blogs/blog-123/posts/post-456');
    }

    public function test_oauth_code_exchange_and_refresh_keep_form_payloads(): void
    {
        Http::fake(function (Request $request) {
            return $request['grant_type'] === 'authorization_code'
                ? Http::response(['access_token' => 'first-token', 'refresh_token' => 'refresh-token', 'expires_in' => 1800])
                : Http::response(['access_token' => 'refreshed-token', 'expires_in' => 3600]);
        });

        $service = app(BloggerOAuthTokenService::class);
        $tokens = $service->exchangeCodeForTokens('authorization-code');
        [$channel] = $this->makeDistribution('refresh-token');
        $accessToken = $service->getValidAccessToken($channel);

        $this->assertSame('refresh-token', $tokens['refresh_token']);
        $this->assertSame(1800, $tokens['expires_in']);
        $this->assertSame('refreshed-token', $accessToken);
        Http::assertSent(fn (Request $request): bool => $request->url() === 'https://oauth2.googleapis.com/token'
            && $request->hasHeader('Content-Type', 'application/x-www-form-urlencoded')
            && $request['grant_type'] === 'authorization_code'
            && $request['code'] === 'authorization-code');
        Http::assertSent(fn (Request $request): bool => $request->url() === 'https://oauth2.googleapis.com/token'
            && $request['grant_type'] === 'refresh_token'
            && $request['refresh_token'] === 'refresh-token');
    }

    public function test_github_image_upload_uses_put_with_base64_json_payload(): void
    {
        Storage::fake('public');
        Storage::disk('public')->put('articles/mdf.png', 'image-bytes');
        config([
            'services.github_image_host.token' => 'github-token',
            'services.github_image_host.repo' => 'owner/images',
            'services.github_image_host.branch' => 'main',
            'services.github_image_host.path_prefix' => 'blogger',
        ]);
        Http::fake(['https://api.github.com/*' => Http::response(['content' => ['sha' => 'abc']], 201)]);

        $output = app(GitHubImageRehostService::class)
            ->rehostLocalImages('<p><img src="/storage/articles/mdf.png" alt="MDF"></p>');

        $this->assertStringContainsString('https://raw.githubusercontent.com/owner/images/main/blogger/', $output);
        Http::assertSent(function (Request $request): bool {
            return $request->method() === 'PUT'
                && str_starts_with($request->url(), 'https://api.github.com/repos/owner/images/contents/blogger/')
                && $request->hasHeader('Authorization', 'Bearer github-token')
                && $request['content'] === base64_encode('image-bytes')
                && $request['branch'] === 'main';
        });
    }

    /** @return array{0:DistributionChannel,1:ArticleDistribution} */
    private function makeDistribution(string $refreshToken = 'refresh-token'): array
    {
        $channel = DistributionChannel::query()->create([
            'name' => 'Blogger',
            'domain' => 'blog.example.com',
            'endpoint_url' => 'https://www.googleapis.com/blogger/v3',
            'channel_type' => 'blogger',
            'channel_config' => ['blogger_blog_id' => 'blog-123'],
            'status' => 'active',
        ]);

        DistributionChannelSecret::query()->create([
            'distribution_channel_id' => (int) $channel->id,
            'key_id' => 'bloauth_test_'.(string) $channel->id,
            'secret_ciphertext' => app(ApiKeyCrypto::class)->encrypt($refreshToken),
            'status' => 'active',
            'scopes' => ['blogger.publish'],
        ]);

        $category = Category::query()->create(['name' => 'Materials', 'slug' => 'materials']);
        $author = Author::query()->create(['name' => 'GEOFlow']);
        $article = Article::query()->create([
            'title' => 'MDF Guide',
            'slug' => 'mdf-guide',
            'content' => 'Body',
            'category_id' => (int) $category->id,
            'author_id' => (int) $author->id,
            'status' => 'published',
            'review_status' => 'approved',
            'published_at' => now(),
        ]);

        $distribution = ArticleDistribution::query()->create([
            'article_id' => (int) $article->id,
            'distribution_channel_id' => (int) $channel->id,
            'action' => 'publish',
            'status' => 'queued',
            'idempotency_key' => 'blogger-test-'.(string) $channel->id,
        ]);

        return [$channel, $distribution];
    }
}
