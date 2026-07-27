<?php

namespace App\Services\GeoFlow;

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
            '/<th(\s[^>]*)?>/u',
            static function (array $matches): string {
                $existingAttrs = trim((string) ($matches[1] ?? ''));

                return '<th style="border:1px solid #ddd;padding:8px;background:#f5f5f5;text-align:left;"'.($existingAttrs !== '' ? ' '.$existingAttrs : '').'>';
            },
            $html
        ) ?? $html;

        $html = preg_replace_callback(
            '/<td(\s[^>]*)?>/u',
            static function (array $matches): string {
                $existingAttrs = trim((string) ($matches[1] ?? ''));

                return '<td style="border:1px solid #ddd;padding:8px;"'.($existingAttrs !== '' ? ' '.$existingAttrs : '').'>';
            },
            $html
        ) ?? $html;

        return $html;
    }
}
