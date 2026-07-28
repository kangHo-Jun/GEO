#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 7: DistributionPublisherManager 등록
09_Blogger연동개발계획.md Phase 7 대응.

Phase 6에서 만든 BloggerPublisher를 실제 채널 라우팅 매핑에 등록합니다.
이 단계가 끝나면 코드 배선(wiring)이 전부 완료됩니다.

실행 위치: geo 프로젝트 루트 (docker-compose.yml이 있는 폴더)
사용법: python3 phase7_manager_registration_patch.py
"""
import os
import sys

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

edit_file(
    "app/Services/GeoFlow/DistributionPublisherManager.php",
    """    public function __construct(
        private readonly GeoFlowAgentPublisher $geoFlowAgentPublisher,
        private readonly WordPressRestPublisher $wordPressRestPublisher,
        private readonly GenericHttpApiPublisher $genericHttpApiPublisher,
    ) {}

    public function forChannel(DistributionChannel $channel): DistributionPublisherInterface
    {
        return match ($channel->channelType()) {
            'geoflow_agent' => $this->geoFlowAgentPublisher,
            'wordpress_rest' => $this->wordPressRestPublisher,
            'generic_http_api' => $this->genericHttpApiPublisher,
            default => throw new RuntimeException('不支持的分发渠道类型：'.(string) $channel->channel_type),
        };
    }""",
    """    public function __construct(
        private readonly GeoFlowAgentPublisher $geoFlowAgentPublisher,
        private readonly WordPressRestPublisher $wordPressRestPublisher,
        private readonly GenericHttpApiPublisher $genericHttpApiPublisher,
        private readonly BloggerPublisher $bloggerPublisher,
    ) {}

    public function forChannel(DistributionChannel $channel): DistributionPublisherInterface
    {
        return match ($channel->channelType()) {
            'geoflow_agent' => $this->geoFlowAgentPublisher,
            'wordpress_rest' => $this->wordPressRestPublisher,
            'generic_http_api' => $this->genericHttpApiPublisher,
            'blogger' => $this->bloggerPublisher,
            default => throw new RuntimeException('不支持的分发渠道类型：'.(string) $channel->channel_type),
        };
    }""",
    "DistributionPublisherManager.php - blogger 매핑 등록",
)

print("")
print("Phase 7 패치 완료. (코드 배선 전체 완료)")
print("다음: docker compose build app && docker compose up -d, 이후 Phase 8(통합 테스트)")