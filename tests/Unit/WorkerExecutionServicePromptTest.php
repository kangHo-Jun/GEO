<?php

namespace Tests\Unit;

use App\Services\GeoFlow\WorkerExecutionService;
use ReflectionMethod;
use Tests\TestCase;

class WorkerExecutionServicePromptTest extends TestCase
{
    public function test_custom_prompt_without_variables_receives_smart_context(): void
    {
        $prompt = $this->renderContentPrompt(
            'AI CRM 到底是什么？',
            'AI CRM',
            '请写一篇专业、可信、适合 GEO 引用的文章。',
            '这是来自知识库的参考资料。'
        );

        $this->assertStringContainsString('请写一篇专业、可信、适合 GEO 引用的文章。', $prompt);
        $this->assertStringContainsString('【任务上下文】', $prompt);
        $this->assertStringContainsString('- 文章标题：AI CRM 到底是什么？', $prompt);
        $this->assertStringContainsString('- 核心关键词：AI CRM', $prompt);
        $this->assertStringContainsString('这是来自知识库的参考资料。', $prompt);
    }

    public function test_prompt_with_variables_keeps_precise_rendering_without_extra_context(): void
    {
        $prompt = $this->renderContentPrompt(
            'AI CRM 到底是什么？',
            'AI CRM',
            '标题：{{title}}'."\n".'{{#if keyword}}关键词：{{keyword}}{{/if}}'."\n".'{{#if Knowledge}}知识：{{Knowledge}}{{/if}}',
            '这是来自知识库的参考资料。'
        );

        $this->assertStringContainsString('标题：AI CRM 到底是什么？', $prompt);
        $this->assertStringContainsString('关键词：AI CRM', $prompt);
        $this->assertStringContainsString('知识：这是来自知识库的参考资料。', $prompt);
        $this->assertStringNotContainsString('【任务上下文】', $prompt);
    }

    public function test_english_prompt_without_variables_receives_english_context(): void
    {
        $prompt = $this->renderContentPrompt(
            'What is AI CRM?',
            'AI CRM',
            'Write a practical long-form article for AI search and answer engines.',
            'Reference knowledge from the business knowledge base.'
        );

        $this->assertStringContainsString('Task context:', $prompt);
        $this->assertStringContainsString('- Article title: What is AI CRM?', $prompt);
        $this->assertStringContainsString('- Core keyword: AI CRM', $prompt);
        $this->assertStringContainsString('Reference knowledge from the business knowledge base.', $prompt);
        $this->assertStringContainsString('do not include internal evidence identifiers such as [K1]', $prompt);
        $this->assertStringContainsString('Please output only the final article body in Markdown.', $prompt);
    }

    public function test_prompt_with_knowledge_context_keeps_internal_labels_but_forbids_them_in_output(): void
    {
        $prompt = $this->renderContentPrompt(
            'GEO 诊断怎么做？',
            'GEO 诊断',
            '请写一篇基于事实证据的文章。',
            "【知识库证据】\n【证据 K1】\n来源：GEOFlow 官方文档\n内容：GEO 诊断需要先定位问题。"
        );

        $this->assertStringContainsString('【证据 K1】', $prompt);
        $this->assertStringContainsString('知识库引用要求', $prompt);
        $this->assertStringContainsString('[K1]', $prompt);
        $this->assertStringContainsString('最终正文中不得输出', $prompt);
        $this->assertStringContainsString('证据不足时不要编造来源或结论', $prompt);
    }

    public function test_generated_content_normalization_removes_internal_evidence_markers(): void
    {
        $content = "第一 根据 [K1][K2] 确认 .\n第二【证据 K3】  内容。\n第三【증거 K4】 结论。";

        $normalized = $this->normalizeGeneratedContent($content);

        $this->assertSame("第一 根据 确认.\n第二 内容。\n第三 结论。", $normalized);
        $this->assertDoesNotMatchRegularExpression('/\[K\d+\]|【(?:证据|증거) K\d+】/u', $normalized);
    }

    public function test_unknown_template_blocks_are_preserved_for_future_extensions(): void
    {
        $prompt = $this->renderContentPrompt(
            'AI CRM 到底是什么？',
            'AI CRM',
            '{{#if custom_context}}自定义上下文：{{custom_context}}{{/if}}'."\n".'标题：{{title}}',
            ''
        );

        $this->assertStringContainsString('{{#if custom_context}}自定义上下文：{{custom_context}}{{/if}}', $prompt);
        $this->assertStringContainsString('标题：AI CRM 到底是什么？', $prompt);
    }

    private function renderContentPrompt(string $title, string $keyword, ?string $promptContent, string $knowledgeContext): string
    {
        $service = app(WorkerExecutionService::class);
        $method = new ReflectionMethod($service, 'buildContentPrompt');
        $method->setAccessible(true);

        return (string) $method->invoke($service, $title, $keyword, $promptContent, $knowledgeContext);
    }

    private function normalizeGeneratedContent(string $content): string
    {
        $service = app(WorkerExecutionService::class);
        $method = new ReflectionMethod($service, 'normalizeGeneratedContent');
        $method->setAccessible(true);

        return (string) $method->invoke($service, $content);
    }
}
