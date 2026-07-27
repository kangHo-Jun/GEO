#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 4 (수정판): Blogger HTML 스타일 보정기
09_Blogger연동개발계획.md Phase 4 대응.

수정 사유: WordPress 채널 코드 확인 결과, 마크다운->HTML 변환은
이미 DistributionPayloadBuilder에서 공통 처리되어 content_html로 넘어옴을 확인.
그래서 별도 마크다운 파서 대신, HTML 스타일 보정만 하는 가벼운 클래스로 재설계.

주의: 이전에 받으셨던 phase4_markdown_converter_patch.py 는 실행하지 마세요.
(MarkdownToBloggerHtmlConverter.php 를 만드는 구버전 - 이 스크립트로 대체됨)

실행 위치: geo 프로젝트 루트 (docker-compose.yml이 있는 폴더)
사용법: python3 phase4_v2_style_adapter_patch.py
"""
import os
import sys

def create_file(path, content, label):
    if os.path.exists(path):
        print(f"SKIP (이미 존재): {label} ({path})")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"OK (신규 생성): {label}")

# 혹시 구버전 파일이 먼저 만들어져 있다면 정리 안내만 하고 건드리지 않음
old_file = "app/Services/GeoFlow/MarkdownToBloggerHtmlConverter.php"
if os.path.exists(old_file):
    print(f"안내: 구버전 파일이 존재합니다 ({old_file}). 이번 패치는 새 파일만 추가하며, 구버전 파일은 건드리지 않습니다. 확인 후 직접 삭제하셔도 됩니다.")

create_file(
    "app/Services/GeoFlow/BloggerContentStyleAdapter.php",
    '''<?php

namespace App\\Services\\GeoFlow;

/**
 * Blogger 발행용 HTML 스타일 보정기.
 *
 * 마크다운 -> HTML 변환은 이미 DistributionPayloadBuilder에서 공통으로 처리되어
 * $payload['article']['content_html']에 담겨 들어온다 (WordPress 채널과 동일한 파이프라인).
 * 이 클래스는 새로 변환하지 않고, GEOFlow 자체 사이트 전용 CSS 클래스
 * (article-table-wrap / article-table)를 Blogger 테마에서도 무난히 보이도록
 * 인라인 스타일로만 바꿔치기한다.
 */
class BloggerContentStyleAdapter
{
    public function adapt(string $contentHtml): string
    {
        $html = preg_replace(
            '/<div class="article-table-wrap"><table class="article-table">/u',
            '<div style="overflow-x:auto;margin:1.5em 0;"><table style="width:100%;border-collapse:collapse;">',
            $contentHtml
        ) ?? $contentHtml;

        $html = preg_replace_callback(
            '/<th(\\s[^>]*)?>/u',
            static function (array $matches): string {
                $existingAttrs = trim((string) ($matches[1] ?? ''));

                return '<th style="border:1px solid #ddd;padding:8px;background:#f5f5f5;text-align:left;"'.($existingAttrs !== '' ? ' '.$existingAttrs : '').'>';
            },
            $html
        ) ?? $html;

        $html = preg_replace_callback(
            '/<td(\\s[^>]*)?>/u',
            static function (array $matches): string {
                $existingAttrs = trim((string) ($matches[1] ?? ''));

                return '<td style="border:1px solid #ddd;padding:8px;"'.($existingAttrs !== '' ? ' '.$existingAttrs : '').'>';
            },
            $html
        ) ?? $html;

        return $html;
    }
}
''',
    "BloggerContentStyleAdapter.php",
)

print("")
print("Phase 4(수정판) 패치 완료.")
print("다음: docker compose build app && docker compose up -d 로 문법 확인, 이후 Phase 5(고정요소) 진행")