#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 8 준비: 관리자 화면에 Blogger 채널 옵션 연결 (UI 배선)
09_Blogger연동개발계획.md Phase 8 대응.

경고: 이 패치가 없으면 Phase 8 통합 테스트를 진행할 수 없습니다.
- channelType() 화이트리스트에 'blogger'가 빠져있던 치명적 버그를 함께 수정합니다.
  (이 버그가 있으면 DB에 blogger로 저장해도 DistributionPublisherManager가
   조용히 geoflow_agent로 되돌려버려서, Blogger 발행이 절대 작동하지 않습니다.)

실행 위치: geo 프로젝트 루트 (docker-compose.yml이 있는 폴더)
사용법: python3 phase8_ui_wiring_patch.py
"""
import os
import sys

def fail(msg):
    print(f"ERROR: {msg}")
    sys.exit(1)

def edit_file(path, old, new, label, allow_missing=False):
    if not os.path.exists(path):
        if allow_missing:
            print(f"SKIP (파일 없음): {label} ({path})")
            return
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
# 1) [치명적 버그 수정] DistributionChannel.php - channelType() 화이트리스트에 blogger 추가
# ---------------------------------------------------------------------------
edit_file(
    "app/Models/DistributionChannel.php",
    """    public function channelType(): string
    {
        $type = (string) ($this->channel_type ?? 'geoflow_agent');

        return in_array($type, ['geoflow_agent', 'wordpress_rest', 'generic_http_api'], true) ? $type : 'geoflow_agent';
    }

    public function isGeoFlowAgent(): bool
    {
        return $this->channelType() === 'geoflow_agent';
    }

    public function isWordPressRest(): bool
    {
        return $this->channelType() === 'wordpress_rest';
    }

    public function isGenericHttpApi(): bool
    {
        return $this->channelType() === 'generic_http_api';
    }""",
    """    public function channelType(): string
    {
        $type = (string) ($this->channel_type ?? 'geoflow_agent');

        return in_array($type, ['geoflow_agent', 'wordpress_rest', 'generic_http_api', 'blogger'], true) ? $type : 'geoflow_agent';
    }

    public function isGeoFlowAgent(): bool
    {
        return $this->channelType() === 'geoflow_agent';
    }

    public function isWordPressRest(): bool
    {
        return $this->channelType() === 'wordpress_rest';
    }

    public function isGenericHttpApi(): bool
    {
        return $this->channelType() === 'generic_http_api';
    }

    public function isBlogger(): bool
    {
        return $this->channelType() === 'blogger';
    }""",
    "DistributionChannel.php - channelType() 화이트리스트 수정 (치명적 버그)",
)

# ---------------------------------------------------------------------------
# 2) DistributionController.php - 검증 규칙 + normalizeChannelConfig blogger 분기
# ---------------------------------------------------------------------------
edit_file(
    "app/Http/Controllers/Admin/DistributionController.php",
    """            'wordpress_username' => ['nullable', 'string', 'max:120'],
            'wordpress_application_password' => ['nullable', 'string', 'max:255'],""",
    """            'wordpress_username' => ['nullable', 'string', 'max:120'],
            'wordpress_application_password' => ['nullable', 'string', 'max:255'],
            'blogger_blog_id' => ['nullable', 'string', 'max:60'],""",
    "DistributionController.php - blogger_blog_id 검증 규칙 추가",
)

edit_file(
    "app/Http/Controllers/Admin/DistributionController.php",
    """        if ($channelType !== 'wordpress_rest') {
            return $this->withExistingFrontendCapabilitiesCache([
                'article_text_ad_policy' => $articleTextAdPolicy,
                'frontend_experience_mode' => $frontendExperienceMode,
            ], $channel);
        }""",
    """        if ($channelType === 'blogger') {
            $defaults = $channel?->resolvedBloggerConfig() ?? (new DistributionChannel)->resolvedBloggerConfig();

            return $this->withExistingFrontendCapabilitiesCache([
                'article_text_ad_policy' => $articleTextAdPolicy,
                'frontend_experience_mode' => $frontendExperienceMode,
                'blogger_blog_id' => trim((string) ($payload['blogger_blog_id'] ?? $defaults['blogger_blog_id'])),
            ], $channel);
        }

        if ($channelType !== 'wordpress_rest') {
            return $this->withExistingFrontendCapabilitiesCache([
                'article_text_ad_policy' => $articleTextAdPolicy,
                'frontend_experience_mode' => $frontendExperienceMode,
            ], $channel);
        }""",
    "DistributionController.php - normalizeChannelConfig() blogger 분기 추가",
)

# ---------------------------------------------------------------------------
# 3) create.blade.php - Blogger 라디오 옵션 + blog_id 입력 패널
# ---------------------------------------------------------------------------
edit_file(
    "resources/views/admin/distribution/create.blade.php",
    """                            <label class="flex cursor-pointer gap-3 rounded-md border border-gray-200 bg-white p-4 hover:border-blue-300">
                                <input type="radio" name="channel_type" value="generic_http_api" class="mt-1 text-blue-600 focus:ring-blue-500" @checked($channelType === 'generic_http_api')>
                                <span>
                                    <span class="block text-sm font-semibold text-gray-900">{{ __('admin.distribution.channel_type.generic_http_api') }}</span>
                                    <span class="mt-1 block text-sm text-gray-600">{{ __('admin.distribution.channel_type.generic_http_api_desc') }}</span>
                                </span>
                            </label>
                        </div>
                    </fieldset>""",
    """                            <label class="flex cursor-pointer gap-3 rounded-md border border-gray-200 bg-white p-4 hover:border-blue-300">
                                <input type="radio" name="channel_type" value="generic_http_api" class="mt-1 text-blue-600 focus:ring-blue-500" @checked($channelType === 'generic_http_api')>
                                <span>
                                    <span class="block text-sm font-semibold text-gray-900">{{ __('admin.distribution.channel_type.generic_http_api') }}</span>
                                    <span class="mt-1 block text-sm text-gray-600">{{ __('admin.distribution.channel_type.generic_http_api_desc') }}</span>
                                </span>
                            </label>
                            <label class="flex cursor-pointer gap-3 rounded-md border border-gray-200 bg-white p-4 hover:border-blue-300">
                                <input type="radio" name="channel_type" value="blogger" class="mt-1 text-blue-600 focus:ring-blue-500" @checked($channelType === 'blogger')>
                                <span>
                                    <span class="block text-sm font-semibold text-gray-900">Blogger</span>
                                    <span class="mt-1 block text-sm text-gray-600">Publish directly to a Blogger blog via Blogger API v3 (OAuth2).</span>
                                </span>
                            </label>
                        </div>
                    </fieldset>""",
    "create.blade.php - Blogger 라디오 옵션 추가",
)

edit_file(
    "resources/views/admin/distribution/create.blade.php",
    """                            <div>
                                <label for="generic_remote_url_path" class="block text-sm font-medium text-gray-700">{{ __('admin.distribution.generic.remote_url_path') }}</label>
                                <input id="generic_remote_url_path" name="generic_remote_url_path" type="text" value="{{ old('generic_remote_url_path', 'url') }}" class="mt-1 block w-full rounded-md border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500" placeholder="data.url">
                            </div>
                        </div>
                    </div>

                    <div data-channel-type-panel="geoflow_agent" @class(['space-y-6', 'hidden' => $channelType !== 'geoflow_agent'])>""",
    """                            <div>
                                <label for="generic_remote_url_path" class="block text-sm font-medium text-gray-700">{{ __('admin.distribution.generic.remote_url_path') }}</label>
                                <input id="generic_remote_url_path" name="generic_remote_url_path" type="text" value="{{ old('generic_remote_url_path', 'url') }}" class="mt-1 block w-full rounded-md border-gray-300 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500" placeholder="data.url">
                            </div>
                        </div>
                    </div>

                    <div data-channel-type-panel="blogger" @class(['rounded-lg border border-orange-100 bg-orange-50 p-5', 'hidden' => $channelType !== 'blogger'])>
                        <div class="mb-5">
                            <h2 class="text-lg font-medium text-gray-900">Blogger settings</h2>
                            <p class="mt-1 text-sm leading-6 text-gray-600">Enter the numeric Blog ID from your Blogger dashboard. OAuth connection is completed after saving, from the channel detail page.</p>
                        </div>
                        <div class="max-w-md">
                            <label for="blogger_blog_id" class="block text-sm font-medium text-gray-700">Blog ID</label>
                            <input id="blogger_blog_id" name="blogger_blog_id" type="text" value="{{ old('blogger_blog_id') }}" class="mt-1 block w-full rounded-md border-gray-300 text-sm shadow-sm focus:border-orange-500 focus:ring-orange-500" placeholder="3911627335922911456">
                        </div>
                    </div>

                    <div data-channel-type-panel="geoflow_agent" @class(['space-y-6', 'hidden' => $channelType !== 'geoflow_agent'])>""",
    "create.blade.php - Blogger 설정 패널(blog_id 입력창) 추가",
)

# ---------------------------------------------------------------------------
# 4) show.blade.php - Blog ID 표시 + Connect Blogger 버튼
# ---------------------------------------------------------------------------
edit_file(
    "resources/views/admin/distribution/show.blade.php",
    """                    @elseif ($channel->isGenericHttpApi())
                        <div>
                            <dt class="text-gray-500">{{ __('admin.distribution.generic.auth_type') }}</dt>
                            <dd class="mt-1 font-medium text-gray-900">{{ __('admin.distribution.generic.auth_'.$genericConfig['generic_auth_type']) }}</dd>
                        </div>
                        <div>
                            <dt class="text-gray-500">{{ __('admin.distribution.generic.publish_endpoint') }}</dt>
                            <dd class="mt-1 break-all font-mono text-sm text-gray-900">{{ $genericConfig['generic_publish_method'] }} {{ $genericConfig['generic_publish_path'] }}</dd>
                        </div>
                    @endif""",
    """                    @elseif ($channel->isGenericHttpApi())
                        <div>
                            <dt class="text-gray-500">{{ __('admin.distribution.generic.auth_type') }}</dt>
                            <dd class="mt-1 font-medium text-gray-900">{{ __('admin.distribution.generic.auth_'.$genericConfig['generic_auth_type']) }}</dd>
                        </div>
                        <div>
                            <dt class="text-gray-500">{{ __('admin.distribution.generic.publish_endpoint') }}</dt>
                            <dd class="mt-1 break-all font-mono text-sm text-gray-900">{{ $genericConfig['generic_publish_method'] }} {{ $genericConfig['generic_publish_path'] }}</dd>
                        </div>
                    @elseif ($channel->isBlogger())
                        <div>
                            <dt class="text-gray-500">Blog ID</dt>
                            <dd class="mt-1 font-mono text-sm text-gray-900">{{ $channel->resolvedBloggerConfig()['blogger_blog_id'] ?: __('admin.common.none') }}</dd>
                        </div>
                        <div>
                            <dt class="text-gray-500">OAuth connection</dt>
                            <dd class="mt-1">
                                <a href="{{ route('admin.distribution.blogger.connect', ['channelId' => $channel->id]) }}" class="inline-flex items-center rounded-md bg-orange-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-orange-700">
                                    Connect Blogger
                                </a>
                            </dd>
                        </div>
                    @endif""",
    "show.blade.php - Blog ID 표시 및 Connect Blogger 버튼 추가",
)

print("")
print("Phase 8 UI 배선 패치 완료.")
print("다음: docker compose build app && docker compose up -d 후, 관리자 화면에서 Blogger 채널 생성/연결/테스트 발행 진행")