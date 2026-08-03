<?php

namespace App\Services\GeoFlow;

use DOMDocument;
use DOMElement;
use DOMNode;

/**
 * 신뢰 뱃지, CTA(견적받기), 회사 서명을 Blogger 발행용 HTML에 고정 위치로 삽입한다.
 *
 * BloggerPublisher::publish() 에서만 호출한다 (발행 직전 단계).
 * WorkerExecutionService.php(로컬 초안 생성 단계)에는 절대 추가하지 않는다.
 * -> GEOFlow 로컬 초안에는 고정요소가 안 붙고, 실제 Blogger로 나가는 순간에만 붙어야
 *    중복 삽입 위험이 없다 (09_Blogger연동개발계획.md Phase 5 설계 원칙).
 *
 * 마크다운이 아니라 이미 변환된 HTML을 다루므로, 문자열 스플릿 대신 DOMDocument로
 * 안전하게 파싱/삽입한다.
 */
class FixedElementInjector
{
    public function inject(string $html): string
    {
        $trustBadgeUrl = trim((string) config('services.blogger.trust_badge_url'));
        $ctaUrl = trim((string) config('services.blogger.cta_url'));

        $html = $this->insertTrustBadge($html, $trustBadgeUrl);
        $html = $this->insertCta($html, $ctaUrl);
        $html = $this->appendSignature($html);

        return $html;
    }

    private function insertTrustBadge(string $html, string $badgeUrl): string
    {
        if ($badgeUrl === '') {
            return $html;
        }

        $badgeHtml = sprintf(
            '<hr style="margin:2em 0;border:none;border-top:1px solid #ddd;" />'
            .'<p style="text-align:center;margin:1.5em 0;"><img src="%s" alt="대산 GS건설 3년 연속 납품업체 신뢰마크" style="max-width:100%%;height:auto;" /></p>',
            htmlspecialchars($badgeUrl, ENT_QUOTES, 'UTF-8')
        );

        return $this->insertBeforePreferredHeading($html, $badgeHtml);
    }

    private function insertCta(string $html, string $ctaUrl): string
    {
        if ($ctaUrl === '') {
            return $html;
        }

        $ctaHtml = sprintf(
            '<div style="text-align:center;margin:2em 0;padding:1.2em;background:#f5f5f5;border-radius:8px;">'
            .'<p style="margin:0 0 0.8em;font-weight:bold;">건축자재 견적이 필요하신가요?</p>'
            .'<a href="%s" style="display:inline-block;padding:0.7em 1.6em;background:#1b2a41;color:#fff;text-decoration:none;border-radius:6px;font-weight:bold;">견적 받기 →</a>'
            .'</div>',
            htmlspecialchars($ctaUrl, ENT_QUOTES, 'UTF-8')
        );

        // 본문 끝에 1회만 삽입 (중간 삽입은 짧은 글에서 끝부분과 겹쳐 중복처럼 보이는 문제가 있어 제거함)
        return $html.$ctaHtml;
    }

    private function appendSignature(string $html): string
    {
        $signatureHtml = '<div style="margin-top:2.5em;padding-top:1.2em;border-top:1px solid #ddd;font-size:0.9em;color:#555;">'
            .'<strong>대산 건축자재</strong><br />'
            .'공식 사이트: <a href="https://daesan.ai">daesan.ai</a>'
            .'</div>';

        return $html.$signatureHtml;
    }

    /**
     * HTML 프래그먼트(<body> 내용물)를 최상위 블록 요소 단위로 다루기 위한
     * 안전한 DOMDocument 파서. 반환값은 (document, body 노드).
     *
     * @return array{0:DOMDocument,1:DOMElement}
     */
    private function parseFragment(string $html): array
    {
        $document = new DOMDocument('1.0', 'UTF-8');
        libxml_use_internal_errors(true);
        // UTF-8 깨짐 방지를 위해 meta charset을 명시적으로 앞에 붙여서 로드
        $document->loadHTML(
            '<?xml encoding="utf-8"?><!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'.$html.'</body></html>',
            LIBXML_NOERROR | LIBXML_NOWARNING
        );
        libxml_clear_errors();

        $body = $document->getElementsByTagName('body')->item(0);
        if (! $body instanceof DOMElement) {
            // 파싱 실패 시 원본을 그대로 감싼 빈 문서 반환 (호출부에서 원본 html로 폴백)
            $fallbackDocument = new DOMDocument('1.0', 'UTF-8');
            $fallbackBody = $fallbackDocument->createElement('body');
            $fallbackDocument->appendChild($fallbackBody);

            return [$fallbackDocument, $fallbackBody];
        }

        return [$document, $body];
    }

    private function serializeBody(DOMDocument $document, DOMElement $body): string
    {
        $output = '';
        foreach (iterator_to_array($body->childNodes) as $child) {
            $output .= $document->saveHTML($child);
        }

        return $output;
    }

    /**
     * FAQ 제목, 결론 제목 순으로 삽입 위치를 찾고, 둘 다 없으면 본문 끝에 삽입한다.
     */
    private function insertBeforePreferredHeading(string $html, string $insertHtml): string
    {
        [$document, $body] = $this->parseFragment($html);

        $headings = array_values(array_filter(
            iterator_to_array($body->childNodes),
            static fn (DOMNode $node): bool => $node instanceof DOMElement
                && preg_match('/^h[1-6]$/i', $node->tagName) === 1
        ));

        $targetHeading = null;
        foreach (['/FAQ/iu', '/결론/u'] as $pattern) {
            foreach ($headings as $heading) {
                if (preg_match($pattern, (string) $heading->textContent) === 1) {
                    $targetHeading = $heading;
                    break 2;
                }
            }
        }

        $this->insertHtmlBeforeNode($document, $body, $targetHeading, $insertHtml);

        return $this->serializeBody($document, $body);
    }

    private function insertHtmlBeforeNode(DOMDocument $document, DOMElement $body, ?DOMNode $referenceNode, string $insertHtml): void
    {
        $fragmentDocument = new DOMDocument('1.0', 'UTF-8');
        libxml_use_internal_errors(true);
        $fragmentDocument->loadHTML(
            '<?xml encoding="utf-8"?><!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'.$insertHtml.'</body></html>',
            LIBXML_NOERROR | LIBXML_NOWARNING
        );
        libxml_clear_errors();

        $fragmentBody = $fragmentDocument->getElementsByTagName('body')->item(0);
        if (! $fragmentBody instanceof DOMElement) {
            return;
        }

        foreach (iterator_to_array($fragmentBody->childNodes) as $node) {
            $imported = $document->importNode($node, true);
            if ($referenceNode !== null) {
                $body->insertBefore($imported, $referenceNode);
            } else {
                $body->appendChild($imported);
            }
        }
    }
}
