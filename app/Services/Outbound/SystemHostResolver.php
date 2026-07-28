<?php

namespace App\Services\Outbound;

use App\Contracts\Outbound\HostResolver;
use Closure;

final class SystemHostResolver implements HostResolver
{
    /** @var Closure(string): array<int, array<string, mixed>> */
    private readonly Closure $lookup;

    /** @param (Closure(string): array<int, array<string, mixed>>)|null $lookup */
    public function __construct(?Closure $lookup = null)
    {
        $this->lookup = $lookup ?? static function (string $host): array {
            // 여러 레코드 타입(DNS_A | DNS_AAAA | DNS_CNAME)을 한 번에 묶어서 조회하면
            // 일부 컨테이너 DNS 환경(Docker 내장 리졸버 등)에서 간헐적으로
            // "temporary server error"가 발생해 전체 조회가 실패하는 문제가 있었다.
            // 타입별로 나누어 조회하고, 한 타입이 실패해도 나머지 타입은
            // 계속 시도하도록 하여 안정성을 높인다(보안 정책 자체는 그대로 유지).
            $records = [];
            foreach ([DNS_A, DNS_AAAA, DNS_CNAME] as $type) {
                try {
                    $result = @dns_get_record($host, $type);
                } catch (\Throwable) {
                    $result = false;
                }

                if (is_array($result)) {
                    $records = [...$records, ...$result];
                }
            }

            return $records;
        };
    }

    public function resolve(string $host): array
    {
        return $this->resolveHost(strtolower(rtrim($host, '.')), [], 0);
    }

    /**
     * @param  array<string, true>  $visited
     * @return list<string>
     */
    private function resolveHost(string $host, array $visited, int $depth): array
    {
        if ($depth > 8 || isset($visited[$host])) {
            return [];
        }

        $visited[$host] = true;
        $addresses = [];
        foreach (($this->lookup)($host) as $record) {
            $type = strtoupper((string) ($record['type'] ?? ''));
            if ($type === 'A' && filter_var($record['ip'] ?? null, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)) {
                $addresses[] = (string) $record['ip'];
            } elseif ($type === 'AAAA' && filter_var($record['ipv6'] ?? null, FILTER_VALIDATE_IP, FILTER_FLAG_IPV6)) {
                $addresses[] = strtolower((string) $record['ipv6']);
            } elseif ($type === 'CNAME') {
                $target = strtolower(rtrim((string) ($record['target'] ?? ''), '.'));
                if ($target !== '') {
                    $addresses = [...$addresses, ...$this->resolveHost($target, $visited, $depth + 1)];
                }
            }
        }

        return array_values(array_unique($addresses));
    }
}
