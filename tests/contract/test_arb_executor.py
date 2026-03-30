from __future__ import annotations

from pathlib import Path

import pytest
from eth_tester.exceptions import TransactionFailed
from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider

pytest.importorskip("solcx")
from solcx import compile_standard, install_solc  # noqa: E402


SOLC_VERSION = "0.8.24"


def _compile_contracts() -> dict:
    root = Path(__file__).resolve().parents[2]
    arb = (root / "contracts" / "ArbExecutor.sol").read_text(encoding="utf-8")
    token = (root / "contracts" / "test" / "MockERC20.sol").read_text(encoding="utf-8")
    router = (root / "contracts" / "test" / "MockRouter.sol").read_text(encoding="utf-8")

    try:
        install_solc(SOLC_VERSION)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"solc install failed: {exc}")

    return compile_standard(
        {
            "language": "Solidity",
            "sources": {
                "ArbExecutor.sol": {"content": arb},
                "MockERC20.sol": {"content": token},
                "MockRouter.sol": {"content": router},
            },
            "settings": {
                "outputSelection": {
                    "*": {
                        "*": ["abi", "evm.bytecode"]
                    }
                }
            },
        },
        solc_version=SOLC_VERSION,
    )


@pytest.fixture(scope="module")
def w3() -> Web3:
    provider = EthereumTesterProvider()
    return Web3(provider)


@pytest.fixture(scope="module")
def compiled() -> dict:
    return _compile_contracts()


def _artifact(compiled: dict, file_name: str, contract_name: str) -> tuple[list[dict], str]:
    item = compiled["contracts"][file_name][contract_name]
    abi = item["abi"]
    bytecode = item["evm"]["bytecode"]["object"]
    return abi, bytecode


def _deploy(w3: Web3, abi: list[dict], bytecode: str, args: list) -> str:
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = contract.constructor(*args).transact({"from": w3.eth.accounts[0]})
    receipt = w3.eth.wait_for_transaction_receipt(tx)
    return receipt.contractAddress


def _build_default_setup(w3: Web3, compiled: dict) -> dict:
    owner = w3.eth.accounts[0]
    other = w3.eth.accounts[1]

    token_abi, token_bytecode = _artifact(compiled, "MockERC20.sol", "MockERC20")
    router_abi, router_bytecode = _artifact(compiled, "MockRouter.sol", "MockRouter")
    arb_abi, arb_bytecode = _artifact(compiled, "ArbExecutor.sol", "ArbExecutor")

    token_a_addr = _deploy(w3, token_abi, token_bytecode, ["USD Coin", "USDC"])
    token_b_addr = _deploy(w3, token_abi, token_bytecode, ["USDt0", "USDT0"])
    router1_addr = _deploy(w3, router_abi, router_bytecode, [])
    router2_addr = _deploy(w3, router_abi, router_bytecode, [])

    token_a = w3.eth.contract(address=token_a_addr, abi=token_abi)
    token_b = w3.eth.contract(address=token_b_addr, abi=token_abi)
    router1 = w3.eth.contract(address=router1_addr, abi=router_abi)
    router2 = w3.eth.contract(address=router2_addr, abi=router_abi)

    init_amount = 100 * 10**18
    leg1_out = 1002 * 10**17
    final_out = 101 * 10**18

    token_a.functions.mint(owner, 1000 * 10**18).transact({"from": owner})
    token_b.functions.mint(router1_addr, 5000 * 10**18).transact({"from": owner})
    token_a.functions.mint(router2_addr, 5000 * 10**18).transact({"from": owner})

    executor_addr = _deploy(w3, arb_abi, arb_bytecode, [[router1_addr, router2_addr], [token_a_addr, token_b_addr]])
    executor = w3.eth.contract(address=executor_addr, abi=arb_abi)

    token_a.functions.approve(executor_addr, init_amount).transact({"from": owner})

    route_id = Web3.keccak(text="route1")
    corr_id = Web3.keccak(text="corr1")

    data1 = router1.encodeABI(fn_name="swap", args=[token_a_addr, token_b_addr, init_amount, leg1_out])
    data2 = router2.encodeABI(fn_name="swap", args=[token_b_addr, token_a_addr, leg1_out, final_out])

    steps = [
        (
            router1_addr,
            token_a_addr,
            token_b_addr,
            Web3.keccak(text="pool-a"),
            5,
            init_amount,
            leg1_out,
            bytes.fromhex(data1[2:]),
        ),
        (
            router2_addr,
            token_b_addr,
            token_a_addr,
            Web3.keccak(text="pool-b"),
            5,
            leg1_out,
            final_out,
            bytes.fromhex(data2[2:]),
        ),
    ]

    return {
        "owner": owner,
        "other": other,
        "token_a": token_a,
        "token_b": token_b,
        "router1": router1,
        "router2": router2,
        "executor": executor,
        "route_id": route_id,
        "corr_id": corr_id,
        "init_amount": init_amount,
        "final_out": final_out,
        "steps": steps,
    }


def test_happy_path_executes(w3: Web3, compiled: dict) -> None:
    s = _build_default_setup(w3, compiled)
    owner = s["owner"]
    token_a = s["token_a"]
    executor = s["executor"]

    bal_before = token_a.functions.balanceOf(owner).call()
    deadline = w3.eth.get_block("latest")["timestamp"] + 60

    tx = executor.functions.executeArb(
        s["route_id"],
        s["corr_id"],
        token_a.address,
        s["init_amount"],
        s["init_amount"] + 5 * 10**17,
        5 * 10**17,
        deadline,
        s["steps"],
    ).transact({"from": owner})
    w3.eth.wait_for_transaction_receipt(tx)

    bal_after = token_a.functions.balanceOf(owner).call()
    assert bal_after > bal_before


def test_min_profit_revert(w3: Web3, compiled: dict) -> None:
    s = _build_default_setup(w3, compiled)
    owner = s["owner"]
    token_a = s["token_a"]
    executor = s["executor"]
    deadline = w3.eth.get_block("latest")["timestamp"] + 60

    with pytest.raises(TransactionFailed):
        executor.functions.executeArb(
            s["route_id"],
            s["corr_id"],
            token_a.address,
            s["init_amount"],
            s["init_amount"] + 2 * 10**18,
            2 * 10**18,
            deadline,
            s["steps"],
        ).transact({"from": owner})


def test_unauthorized_revert(w3: Web3, compiled: dict) -> None:
    s = _build_default_setup(w3, compiled)
    token_a = s["token_a"]
    executor = s["executor"]
    deadline = w3.eth.get_block("latest")["timestamp"] + 60

    with pytest.raises(TransactionFailed):
        executor.functions.executeArb(
            s["route_id"],
            s["corr_id"],
            token_a.address,
            s["init_amount"],
            s["init_amount"],
            0,
            deadline,
            s["steps"],
        ).transact({"from": s["other"]})


def test_non_allowlisted_router_revert(w3: Web3, compiled: dict) -> None:
    s = _build_default_setup(w3, compiled)
    owner = s["owner"]
    token_a = s["token_a"]
    executor = s["executor"]
    deadline = w3.eth.get_block("latest")["timestamp"] + 60

    unknown_router = w3.eth.accounts[9]
    bad_steps = list(s["steps"])
    bad_steps[1] = (
        unknown_router,
        bad_steps[1][1],
        bad_steps[1][2],
        bad_steps[1][3],
        bad_steps[1][4],
        bad_steps[1][5],
        bad_steps[1][6],
        bad_steps[1][7],
    )

    with pytest.raises(TransactionFailed):
        executor.functions.executeArb(
            s["route_id"],
            s["corr_id"],
            token_a.address,
            s["init_amount"],
            s["init_amount"],
            0,
            deadline,
            bad_steps,
        ).transact({"from": owner})


def test_paused_revert(w3: Web3, compiled: dict) -> None:
    s = _build_default_setup(w3, compiled)
    owner = s["owner"]
    token_a = s["token_a"]
    executor = s["executor"]
    deadline = w3.eth.get_block("latest")["timestamp"] + 60

    executor.functions.pause().transact({"from": owner})

    with pytest.raises(TransactionFailed):
        executor.functions.executeArb(
            s["route_id"],
            s["corr_id"],
            token_a.address,
            s["init_amount"],
            s["init_amount"],
            0,
            deadline,
            s["steps"],
        ).transact({"from": owner})


def test_emergency_withdraw(w3: Web3, compiled: dict) -> None:
    s = _build_default_setup(w3, compiled)
    owner = s["owner"]
    token_a = s["token_a"]
    executor = s["executor"]

    token_a.functions.transfer(executor.address, 10 * 10**18).transact({"from": owner})
    before = token_a.functions.balanceOf(owner).call()

    executor.functions.emergencyWithdraw(token_a.address, 10 * 10**18, owner).transact({"from": owner})
    after = token_a.functions.balanceOf(owner).call()

    assert after > before
