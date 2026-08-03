<?php

namespace Tests\Unit;

use App\Services\GeoFlow\FixedElementInjector;
use DOMDocument;
use DOMElement;
use ReflectionMethod;
use Tests\TestCase;

class FixedElementInjectorTest extends TestCase
{
    private const BADGE_URL = 'https://example.com/trust-badge.png';

    public function test_badge_is_inserted_immediately_before_faq_heading(): void
    {
        $html = '<h2>결론 및 정리</h2><p>결론 내용</p><h2>자주 묻는 질문 (faq)</h2><p>FAQ 내용</p>';

        $output = $this->insertTrustBadge($html, self::BADGE_URL);

        $this->assertBadgeImmediatelyBeforeHeading($output, 'faq');
    }

    public function test_badge_is_inserted_immediately_before_conclusion_when_faq_is_absent(): void
    {
        $html = '<h2>사용법</h2><p>본문</p><h3>결론과 제안</h3><p>마무리</p>';

        $output = $this->insertTrustBadge($html, self::BADGE_URL);

        $this->assertBadgeImmediatelyBeforeHeading($output, '결론');
    }

    public function test_badge_is_appended_to_body_when_no_preferred_heading_exists(): void
    {
        $html = '<h2>사용법</h2><p>본문</p>';

        $output = $this->insertTrustBadge($html, self::BADGE_URL);
        [, $body] = $this->parse($output);
        $elements = $this->topLevelElements($body);

        $this->assertSame('hr', $elements[count($elements) - 2]->tagName);
        $this->assertSame('p', $elements[count($elements) - 1]->tagName);
        $this->assertSame(self::BADGE_URL, $elements[count($elements) - 1]->getElementsByTagName('img')->item(0)?->getAttribute('src'));
    }

    public function test_empty_badge_url_leaves_content_unchanged(): void
    {
        $html = '<h2>FAQ</h2><p>본문</p>';

        $this->assertSame($html, $this->insertTrustBadge($html, ''));
    }

    public function test_badge_is_inserted_exactly_once(): void
    {
        $output = $this->insertTrustBadge('<p>본문</p><h2>FAQ 자주 묻는 질문</h2>', self::BADGE_URL);

        $this->assertSame(1, substr_count($output, self::BADGE_URL));
        $this->assertSame(1, substr_count($output, '대산 GS건설 3년 연속 납품업체 신뢰마크'));
    }

    public function test_original_table_and_list_structure_is_preserved(): void
    {
        $html = '<table><thead><tr><th>항목</th><th>값</th></tr></thead><tbody><tr><td>MDF</td><td>적합</td></tr></tbody></table>'
            .'<ul><li>상위<ul><li>하위</li></ul></li></ul><h2>FAQ</h2>';

        $output = $this->insertTrustBadge($html, self::BADGE_URL);
        [$document] = $this->parse($output);

        $this->assertSame(1, $document->getElementsByTagName('table')->length);
        $this->assertSame(2, $document->getElementsByTagName('th')->length);
        $this->assertSame(2, $document->getElementsByTagName('td')->length);
        $this->assertSame(2, $document->getElementsByTagName('ul')->length);
        $this->assertSame(2, $document->getElementsByTagName('li')->length);
        $this->assertStringContainsString('MDF', $output);
        $this->assertStringContainsString('하위', $output);
    }

    private function insertTrustBadge(string $html, string $badgeUrl): string
    {
        $method = new ReflectionMethod(FixedElementInjector::class, 'insertTrustBadge');
        $method->setAccessible(true);

        return (string) $method->invoke(app(FixedElementInjector::class), $html, $badgeUrl);
    }

    private function assertBadgeImmediatelyBeforeHeading(string $html, string $headingText): void
    {
        [, $body] = $this->parse($html);
        $elements = $this->topLevelElements($body);
        $headingIndex = null;

        foreach ($elements as $index => $element) {
            if (preg_match('/^h[1-6]$/i', $element->tagName) === 1
                && mb_stripos($element->textContent, $headingText, 0, 'UTF-8') !== false) {
                $headingIndex = $index;
                break;
            }
        }

        $this->assertNotNull($headingIndex);
        $this->assertGreaterThanOrEqual(2, $headingIndex);
        $this->assertSame('hr', $elements[$headingIndex - 2]->tagName);
        $this->assertSame('p', $elements[$headingIndex - 1]->tagName);
        $this->assertSame(self::BADGE_URL, $elements[$headingIndex - 1]->getElementsByTagName('img')->item(0)?->getAttribute('src'));
    }

    /** @return array{0:DOMDocument,1:DOMElement} */
    private function parse(string $html): array
    {
        $document = new DOMDocument('1.0', 'UTF-8');
        libxml_use_internal_errors(true);
        $document->loadHTML('<?xml encoding="utf-8"?><html><body>'.$html.'</body></html>');
        libxml_clear_errors();

        /** @var DOMElement $body */
        $body = $document->getElementsByTagName('body')->item(0);

        return [$document, $body];
    }

    /** @return list<DOMElement> */
    private function topLevelElements(DOMElement $body): array
    {
        return array_values(array_filter(
            iterator_to_array($body->childNodes),
            static fn ($node): bool => $node instanceof DOMElement
        ));
    }
}
