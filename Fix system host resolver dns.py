#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SystemHostResolver DNS 조회 안정성 수정

증상: GitHub API 등 외부 요청 시
  "dns_get_record(): A temporary server error occurred"
  "Outbound request blocked by security policy"

원인: DNS_A | DNS_AAAA | DNS_CNAME 를 한 번에 묶어서 조회하는 방식이
Docker 내장 DNS 리졸버 환경에서 간헐적으로 실패함. 보안 정책 자체(SSRF 방지)는
정상 설계이고 그대로 유지하며, 그 밑단 DNS 조회 함수의 안정성만 개선한다.

수정: 레코드 타입을 개별로 나누어 조회, 한 타입이 실패해도 나머지는 계속 시도.

실행 위치: geo 프로젝트 루트 (docker-compose.yml이 있는 폴더)
사용법: python3 fix_system_host_resolver_dns.py
"""
import os
import json

def overwrite_file(path, content, label):
    if not os.path.exists(path):
        print(f"ERROR: {label}: 파일이 없습니다 ({path})")
        raise SystemExit(1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"OK (덮어쓰기): {label}")

FILE_CONTENT = json.loads('"<?php\\n\\nnamespace App\\\\Services\\\\Outbound;\\n\\nuse App\\\\Contracts\\\\Outbound\\\\HostResolver;\\nuse Closure;\\n\\nfinal class SystemHostResolver implements HostResolver\\n{\\n    /** @var Closure(string): array<int, array<string, mixed>> */\\n    private readonly Closure $lookup;\\n\\n    /** @param (Closure(string): array<int, array<string, mixed>>)|null $lookup */\\n    public function __construct(?Closure $lookup = null)\\n    {\\n        $this->lookup = $lookup ?? static function (string $host): array {\\n            // \\uc5ec\\ub7ec \\ub808\\ucf54\\ub4dc \\ud0c0\\uc785(DNS_A | DNS_AAAA | DNS_CNAME)\\uc744 \\ud55c \\ubc88\\uc5d0 \\ubb36\\uc5b4\\uc11c \\uc870\\ud68c\\ud558\\uba74\\n            // \\uc77c\\ubd80 \\ucee8\\ud14c\\uc774\\ub108 DNS \\ud658\\uacbd(Docker \\ub0b4\\uc7a5 \\ub9ac\\uc878\\ubc84 \\ub4f1)\\uc5d0\\uc11c \\uac04\\ud5d0\\uc801\\uc73c\\ub85c\\n            // \\"temporary server error\\"\\uac00 \\ubc1c\\uc0dd\\ud574 \\uc804\\uccb4 \\uc870\\ud68c\\uac00 \\uc2e4\\ud328\\ud558\\ub294 \\ubb38\\uc81c\\uac00 \\uc788\\uc5c8\\ub2e4.\\n            // \\ud0c0\\uc785\\ubcc4\\ub85c \\ub098\\ub204\\uc5b4 \\uc870\\ud68c\\ud558\\uace0, \\ud55c \\ud0c0\\uc785\\uc774 \\uc2e4\\ud328\\ud574\\ub3c4 \\ub098\\uba38\\uc9c0 \\ud0c0\\uc785\\uc740\\n            // \\uacc4\\uc18d \\uc2dc\\ub3c4\\ud558\\ub3c4\\ub85d \\ud558\\uc5ec \\uc548\\uc815\\uc131\\uc744 \\ub192\\uc778\\ub2e4(\\ubcf4\\uc548 \\uc815\\ucc45 \\uc790\\uccb4\\ub294 \\uadf8\\ub300\\ub85c \\uc720\\uc9c0).\\n            $records = [];\\n            foreach ([DNS_A, DNS_AAAA, DNS_CNAME] as $type) {\\n                try {\\n                    $result = @dns_get_record($host, $type);\\n                } catch (\\\\Throwable) {\\n                    $result = false;\\n                }\\n\\n                if (is_array($result)) {\\n                    $records = [...$records, ...$result];\\n                }\\n            }\\n\\n            return $records;\\n        };\\n    }\\n\\n    public function resolve(string $host): array\\n    {\\n        return $this->resolveHost(strtolower(rtrim($host, \'.\')), [], 0);\\n    }\\n\\n    /**\\n     * @param  array<string, true>  $visited\\n     * @return list<string>\\n     */\\n    private function resolveHost(string $host, array $visited, int $depth): array\\n    {\\n        if ($depth > 8 || isset($visited[$host])) {\\n            return [];\\n        }\\n\\n        $visited[$host] = true;\\n        $addresses = [];\\n        foreach (($this->lookup)($host) as $record) {\\n            $type = strtoupper((string) ($record[\'type\'] ?? \'\'));\\n            if ($type === \'A\' && filter_var($record[\'ip\'] ?? null, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) {\\n                $addresses[] = (string) $record[\'ip\'];\\n            } elseif ($type === \'AAAA\' && filter_var($record[\'ipv6\'] ?? null, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6)) {\\n                $addresses[] = strtolower((string) $record[\'ipv6\']);\\n            } elseif ($type === \'CNAME\') {\\n                $target = strtolower(rtrim((string) ($record[\'target\'] ?? \'\'), \'.\'));\\n                if ($target !== \'\') {\\n                    $addresses = [...$addresses, ...$this->resolveHost($target, $visited, $depth + 1)];\\n                }\\n            }\\n        }\\n\\n        return array_values(array_unique($addresses));\\n    }\\n}\\n"')

overwrite_file(
    "app/Services/Outbound/SystemHostResolver.php",
    FILE_CONTENT,
    "SystemHostResolver.php (DNS 조회 타입별 분리, 개별 실패 허용)",
)

print("")
print("패치 완료.")
print("다음: docker compose build app && docker compose up -d 후 GitHub 이미지 재호스팅 재시도")