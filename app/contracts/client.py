from __future__ import annotations

from dataclasses import dataclass

from web3 import Web3

from app.config.settings import Settings


@dataclass(slots=True)
class ArbRouteCall:
    router_a: str
    router_b: str
    token_start: str
    token_mid: str
    amount_in: int
    min_amount_out_final: int
    deadline: int


class ArbExecutorClient:
    def __init__(self, settings: Settings, rpc_url: str | None = None) -> None:
        self.settings = settings
        self.rpc_url = rpc_url or settings.hyperevm_rpc_url
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

    def validate_chain(self) -> bool:
        try:
            chain_id = self.w3.eth.chain_id
        except Exception:
            return False
        return chain_id == self.settings.hyperevm_chain_id

    def validate_address(self, value: str) -> bool:
        try:
            _ = Web3.to_checksum_address(value)
            return True
        except Exception:
            return False

    def validate_allowlist(self, route_call: ArbRouteCall) -> tuple[bool, str]:
        router_a = route_call.router_a.lower()
        router_b = route_call.router_b.lower()
        token_start = route_call.token_start.lower()
        token_mid = route_call.token_mid.lower()

        if router_a not in self.settings.allowlisted_routers_set:
            return False, "router_a_not_allowlisted"
        if router_b not in self.settings.allowlisted_routers_set:
            return False, "router_b_not_allowlisted"
        if token_start not in self.settings.allowlisted_tokens_set:
            return False, "token_start_not_allowlisted"
        if token_mid not in self.settings.allowlisted_tokens_set:
            return False, "token_mid_not_allowlisted"
        return True, ""

    def dry_run(self, route_call: ArbRouteCall) -> tuple[bool, str]:
        if not self.validate_chain():
            return False, "chain_id_mismatch"
        for address in (route_call.router_a, route_call.router_b, route_call.token_start, route_call.token_mid):
            if not self.validate_address(address):
                return False, "invalid_address"
        ok, reason = self.validate_allowlist(route_call)
        if not ok:
            return False, reason
        if route_call.amount_in <= 0:
            return False, "invalid_amount"
        if route_call.deadline <= 0:
            return False, "deadline_required"
        return True, "ok"