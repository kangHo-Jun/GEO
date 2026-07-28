#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub 이미지 재호스팅 기능 추가

문제: GEOFlow가 localhost에서만 돌아가서, Image Library 사진이
Blogger에서 깨져 보임 (외부 인터넷에서 접근 불가한 상대경로).
Blogger API에는 이미지 업로드 엔드포인트 자체가 없음(공식 확인됨).

해결: 발행 직전, 로컬 이미지를 공개 GitHub 저장소에 업로드하고
raw.githubusercontent.com 공개 URL로 교체 (신뢰뱃지와 동일한 방식).

파이프라인 순서: 스타일 보정 -> [신규] 이미지 재호스팅 -> 고정요소(뱃지) 삽입
(뱃지 위치 계산이 "본문 이미지가 속한 섹션 끝"을 찾으므로, 이 시점엔
이미지가 이미 공개 URL이어야 정상 작동함)

실행 위치: geo 프로젝트 루트 (docker-compose.yml이 있는 폴더)
사용법: python3 add_github_image_rehost.py
"""
import os
import sys
import json

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

# 1) config/services.php - github_image_host 설정 블록 추가
edit_file(
    "config/services.php",
    "    'blogger' => [\n        'client_id' => env('BLOGGER_OAUTH_CLIENT_ID'),\n        'client_secret' => env('BLOGGER_OAUTH_CLIENT_SECRET'),\n        'redirect_uri' => env('BLOGGER_OAUTH_REDIRECT_URI'),\n        'trust_badge_url' => env('BLOGGER_TRUST_BADGE_URL'),\n        'cta_url' => env('BLOGGER_CTA_URL', 'https://web-cadalog-ver10.vercel.app/'),\n    ],",
    "    'blogger' => [\n        'client_id' => env('BLOGGER_OAUTH_CLIENT_ID'),\n        'client_secret' => env('BLOGGER_OAUTH_CLIENT_SECRET'),\n        'redirect_uri' => env('BLOGGER_OAUTH_REDIRECT_URI'),\n        'trust_badge_url' => env('BLOGGER_TRUST_BADGE_URL'),\n        'cta_url' => env('BLOGGER_CTA_URL', 'https://web-cadalog-ver10.vercel.app/'),\n    ],\n\n    'github_image_host' => [\n        'token' => env('GITHUB_IMAGE_HOST_TOKEN'),\n        'repo' => env('GITHUB_IMAGE_HOST_REPO', 'kangHo-Jun/Blogger-Automation'),\n        'branch' => env('GITHUB_IMAGE_HOST_BRANCH', 'main'),\n        'path_prefix' => env('GITHUB_IMAGE_HOST_PATH_PREFIX', 'assets/generated'),\n    ],",
    "config/services.php - github_image_host 설정 추가",
)

# 2) GitHubImageRehostService.php 신규 생성
REHOST_CONTENT = json.loads('"<?php\\n\\nnamespace App\\\\Services\\\\GeoFlow;\\n\\nuse Illuminate\\\\Support\\\\Facades\\\\Http;\\nuse Illuminate\\\\Support\\\\Facades\\\\Storage;\\nuse RuntimeException;\\n\\n/**\\n * GEOFlow\\ub294 localhost(\\uc678\\ubd80 \\uc778\\ud130\\ub137\\uc5d0\\uc11c \\uc811\\uadfc \\ubd88\\uac00)\\uc5d0\\uc11c \\ub3cc\\uc544\\uac00\\ubbc0\\ub85c,\\n * Image Library \\uc0ac\\uc9c4\\uc758 \\uc0c1\\ub300\\uacbd\\ub85c(/storage/...)\\ub97c Blogger \\ubcf8\\ubb38\\uc5d0 \\uadf8\\ub300\\ub85c \\ub123\\uc73c\\uba74\\n * \\uc774\\ubbf8\\uc9c0\\uac00 \\uae68\\uc9c4\\ub2e4 (Blogger API\\ub294 \\uc774\\ubbf8\\uc9c0 \\uc5c5\\ub85c\\ub4dc \\uc5d4\\ub4dc\\ud3ec\\uc778\\ud2b8 \\uc790\\uccb4\\ub97c \\uc81c\\uacf5\\ud558\\uc9c0 \\uc54a\\uc74c).\\n *\\n * \\ud574\\uacb0: \\ubc1c\\ud589 \\uc9c1\\uc804, \\ub85c\\uceec \\uc774\\ubbf8\\uc9c0\\ub97c \\uacf5\\uac1c GitHub \\uc800\\uc7a5\\uc18c\\uc5d0 \\uc5c5\\ub85c\\ub4dc\\ud558\\uace0\\n * raw.githubusercontent.com \\uacf5\\uac1c URL\\ub85c \\uad50\\uccb4\\ud55c\\ub2e4 (\\uc2e0\\ub8b0\\ubc43\\uc9c0\\uc640 \\ub3d9\\uc77c\\ud55c \\ud638\\uc2a4\\ud305 \\ubc29\\uc2dd).\\n */\\nclass GitHubImageRehostService\\n{\\n    /**\\n     * HTML \\uc548\\uc758 \\ub85c\\uceec(/storage/...) <img src>\\ub97c \\uc804\\ubd80 \\ucc3e\\uc544 GitHub\\uc5d0 \\uc5c5\\ub85c\\ub4dc\\ud558\\uace0,\\n     * \\uacf5\\uac1c URL\\ub85c \\uce58\\ud658\\ud55c HTML\\uc744 \\ubc18\\ud658\\ud55c\\ub2e4.\\n     */\\n    public function rehostLocalImages(string $html): string\\n    {\\n        $token = trim((string) config(\'services.github_image_host.token\'));\\n        if ($token === \'\') {\\n            // \\ud1a0\\ud070 \\ubbf8\\uc124\\uc815 \\uc2dc \\uc6d0\\ubcf8 \\uadf8\\ub300\\ub85c \\ubc18\\ud658 (\\uc548\\uc804\\ud55c \\ud3f4\\ubc31, \\ubc1c\\ud589 \\uc790\\uccb4\\ub97c \\ub9c9\\uc9c0 \\uc54a\\uc74c)\\n            return $html;\\n        }\\n\\n        return preg_replace_callback(\\n            \'/<img\\\\s+([^>]*?)src=\\"(\\\\/storage\\\\/[^\\"]+)\\"([^>]*)>/u\',\\n            function (array $matches) use ($token): string {\\n                [, $before, $localSrc, $after] = $matches;\\n\\n                try {\\n                    $publicUrl = $this->uploadLocalImage($localSrc, $token);\\n                } catch (RuntimeException) {\\n                    // \\uc5c5\\ub85c\\ub4dc \\uc2e4\\ud328 \\uc2dc \\uc6d0\\ubcf8 \\ud0dc\\uadf8\\ub97c \\uadf8\\ub300\\ub85c \\ub454\\ub2e4 (\\ubc1c\\ud589 \\uc790\\uccb4\\ub294 \\uacc4\\uc18d \\uc9c4\\ud589)\\n                    return $matches[0];\\n                }\\n\\n                return \'<img \'.$before.\'src=\\"\'.$publicUrl.\'\\"\'.$after.\'>\';\\n            },\\n            $html\\n        ) ?? $html;\\n    }\\n\\n    private function uploadLocalImage(string $localSrc, string $token): string\\n    {\\n        $diskPath = ltrim((string) preg_replace(\'#^/storage/#\', \'\', $localSrc), \'/\');\\n        if ($diskPath === \'\' || ! Storage::disk(\'public\')->exists($diskPath)) {\\n            throw new RuntimeException(\'\\ub85c\\uceec \\uc774\\ubbf8\\uc9c0 \\ud30c\\uc77c\\uc744 \\ucc3e\\uc744 \\uc218 \\uc5c6\\uc2b5\\ub2c8\\ub2e4: \'.$localSrc);\\n        }\\n\\n        $bytes = Storage::disk(\'public\')->get($diskPath);\\n        $repo = trim((string) config(\'services.github_image_host.repo\'));\\n        $branch = trim((string) config(\'services.github_image_host.branch\'));\\n        $pathPrefix = trim((string) config(\'services.github_image_host.path_prefix\'), \'/\');\\n\\n        $fileName = date(\'Ymd_His\').\'_\'.bin2hex(random_bytes(4)).\'_\'.basename($diskPath);\\n        $remotePath = $pathPrefix.\'/\'.$fileName;\\n\\n        $response = Http::withHeaders([\\n            \'Authorization\' => \'Bearer \'.$token,\\n            \'Accept\' => \'application/vnd.github+json\',\\n        ])->put(\'https://api.github.com/repos/\'.$repo.\'/contents/\'.$remotePath, [\\n            \'message\' => \'GEOFlow: Blogger \\ubc1c\\ud589\\uc6a9 \\uc774\\ubbf8\\uc9c0 \\uc790\\ub3d9 \\uc5c5\\ub85c\\ub4dc (\'.$fileName.\')\',\\n            \'content\' => base64_encode($bytes),\\n            \'branch\' => $branch,\\n        ]);\\n\\n        if ($response->failed()) {\\n            throw new RuntimeException(\'GitHub \\uc774\\ubbf8\\uc9c0 \\uc5c5\\ub85c\\ub4dc \\uc2e4\\ud328: \'.$response->body());\\n        }\\n\\n        return \'https://raw.githubusercontent.com/\'.$repo.\'/\'.$branch.\'/\'.$remotePath;\\n    }\\n}\\n"')
create_file(
    "app/Services/GeoFlow/GitHubImageRehostService.php",
    REHOST_CONTENT,
    "GitHubImageRehostService.php",
)

# 3) BloggerPublisher.php - 의존성 주입 + 파이프라인 순서 수정
edit_file(
    "app/Services/GeoFlow/BloggerPublisher.php",
    "/**\n * Blogger API v3 발행 어댑터.\n *\n * 09_Blogger연동개발계획.md Phase 6 대응.\n * WordPressRestPublisher와 동일한 계약(DistributionPublisherInterface)을 따르며,\n * Task/Distribution 쪽 기존 코드는 전혀 수정하지 않는다.\n *\n * 파이프라인: OAuth 토큰 확보 -> HTML 스타일 보정 -> 고정요소 삽입 -> Blogger API 호출\n */\nclass BloggerPublisher implements DistributionPublisherInterface\n{\n    private const API_BASE = 'https://www.googleapis.com/blogger/v3';\n\n    public function __construct(\n        private readonly BloggerOAuthTokenService $tokenService,\n        private readonly BloggerContentStyleAdapter $styleAdapter,\n        private readonly FixedElementInjector $elementInjector,\n    ) {}",
    '/**\n * Blogger API v3 발행 어댑터.\n *\n * 09_Blogger연동개발계획.md Phase 6 대응.\n * WordPressRestPublisher와 동일한 계약(DistributionPublisherInterface)을 따르며,\n * Task/Distribution 쪽 기존 코드는 전혀 수정하지 않는다.\n *\n * 파이프라인: OAuth 토큰 확보 -> HTML 스타일 보정 -> 로컬 이미지 GitHub 재호스팅\n *           -> 고정요소 삽입(뱃지/CTA/서명) -> Blogger API 호출\n *\n * 재호스팅이 고정요소 삽입보다 먼저인 이유: FixedElementInjector가 "본문 이미지가 속한\n * 섹션 끝"을 찾아 뱃지를 배치하는데, 이 시점엔 이미지가 이미 공개 URL이어야\n * 정상적으로 <img> 태그로 인식된다.\n */\nclass BloggerPublisher implements DistributionPublisherInterface\n{\n    private const API_BASE = \'https://www.googleapis.com/blogger/v3\';\n\n    public function __construct(\n        private readonly BloggerOAuthTokenService $tokenService,\n        private readonly BloggerContentStyleAdapter $styleAdapter,\n        private readonly GitHubImageRehostService $imageRehostService,\n        private readonly FixedElementInjector $elementInjector,\n    ) {}',
    "BloggerPublisher.php - GitHubImageRehostService 의존성 추가",
)

edit_file(
    "app/Services/GeoFlow/BloggerPublisher.php",
    '        $contentHtml = $this->styleAdapter->adapt($contentHtml);\n        $contentHtml = $this->elementInjector->inject($contentHtml);',
    '        $contentHtml = $this->styleAdapter->adapt($contentHtml);\n        $contentHtml = $this->imageRehostService->rehostLocalImages($contentHtml);\n        $contentHtml = $this->elementInjector->inject($contentHtml);',
    "BloggerPublisher.php - 이미지 재호스팅을 파이프라인에 연결",
)

print("")
print("패치 완료.")
print("다음: .env에 GITHUB_IMAGE_HOST_TOKEN 추가 -> docker compose build app && docker compose up -d")