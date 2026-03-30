// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract ArbExecutor {
    struct SwapStep {
        address router;
        address tokenIn;
        address tokenOut;
        bytes32 poolId;
        uint24 feeTier;
        uint256 amountIn; // 0 means use full current amount
        uint256 minAmountOut;
        bytes data;
    }

    event ArbExecuted(
        bytes32 indexed routeId,
        address indexed startToken,
        uint256 initialAmount,
        uint256 finalAmount,
        uint256 profit,
        uint256 gasUsed,
        bytes32 correlationId
    );
    event ArbRevertedReason(bytes32 indexed routeId, string reason);
    event Paused(address indexed by);
    event Unpaused(address indexed by);

    address public owner;
    bool public paused;

    mapping(address => bool) public allowlistedRouters;
    mapping(address => bool) public allowlistedTokens;

    uint256 private _status;
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;

    error Unauthorized();
    error PausedError();
    error InvalidDeadline();
    error InvalidPath();
    error NotAllowlistedRouter(address router);
    error NotAllowlistedToken(address token);
    error InsufficientOutput(uint256 actual, uint256 minExpected);
    error FinalTokenMismatch();
    error MinProfitNotMet(uint256 finalAmount, uint256 minFinal, uint256 profit, uint256 minProfit);
    error RouterCallFailed(bytes reason);

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    modifier nonReentrant() {
        require(_status != _ENTERED, "reentrant");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }

    modifier whenNotPaused() {
        if (paused) revert PausedError();
        _;
    }

    constructor(address[] memory routers, address[] memory tokens) {
        owner = msg.sender;
        _status = _NOT_ENTERED;

        for (uint256 i = 0; i < routers.length; i++) {
            allowlistedRouters[routers[i]] = true;
        }
        for (uint256 i = 0; i < tokens.length; i++) {
            allowlistedTokens[tokens[i]] = true;
        }
    }

    function setAllowlistedRouter(address router, bool allowed) external onlyOwner {
        allowlistedRouters[router] = allowed;
    }

    function setAllowlistedToken(address token, bool allowed) external onlyOwner {
        allowlistedTokens[token] = allowed;
    }

    function pause() external onlyOwner {
        paused = true;
        emit Paused(msg.sender);
    }

    function unpause() external onlyOwner {
        paused = false;
        emit Unpaused(msg.sender);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "zero-owner");
        owner = newOwner;
    }

    function emergencyWithdraw(address token, uint256 amount, address to) external onlyOwner nonReentrant {
        require(to != address(0), "zero-to");
        _safeTransfer(token, to, amount);
    }

    function executeArb(
        bytes32 routeId,
        bytes32 correlationId,
        address startToken,
        uint256 initialAmount,
        uint256 minAmountOutFinal,
        uint256 minProfitAbsolute,
        uint256 deadline,
        SwapStep[] calldata steps
    ) external onlyOwner nonReentrant whenNotPaused returns (uint256 finalAmount, uint256 profit) {
        if (deadline < block.timestamp) {
            emit ArbRevertedReason(routeId, "deadline_expired");
            revert InvalidDeadline();
        }
        if (steps.length == 0) {
            emit ArbRevertedReason(routeId, "empty_steps");
            revert InvalidPath();
        }
        if (!allowlistedTokens[startToken]) {
            emit ArbRevertedReason(routeId, "start_token_not_allowlisted");
            revert NotAllowlistedToken(startToken);
        }

        uint256 gasStart = gasleft();

        _safeTransferFrom(startToken, msg.sender, address(this), initialAmount);

        address currentToken = startToken;
        uint256 currentAmount = initialAmount;

        for (uint256 i = 0; i < steps.length; i++) {
            SwapStep calldata step = steps[i];

            if (!allowlistedRouters[step.router]) {
                emit ArbRevertedReason(routeId, "router_not_allowlisted");
                revert NotAllowlistedRouter(step.router);
            }
            if (!allowlistedTokens[step.tokenIn] || !allowlistedTokens[step.tokenOut]) {
                emit ArbRevertedReason(routeId, "token_not_allowlisted");
                revert NotAllowlistedToken(!allowlistedTokens[step.tokenIn] ? step.tokenIn : step.tokenOut);
            }
            if (step.tokenIn != currentToken) {
                emit ArbRevertedReason(routeId, "token_path_mismatch");
                revert InvalidPath();
            }

            uint256 amountIn = step.amountIn == 0 ? currentAmount : step.amountIn;
            if (amountIn > currentAmount) {
                emit ArbRevertedReason(routeId, "amount_in_exceeds_balance");
                revert InvalidPath();
            }

            uint256 beforeOut = IERC20(step.tokenOut).balanceOf(address(this));

            _safeApprove(step.tokenIn, step.router, amountIn);
            (bool ok, bytes memory retData) = step.router.call(step.data);
            if (!ok) {
                emit ArbRevertedReason(routeId, "router_call_failed");
                revert RouterCallFailed(retData);
            }

            uint256 afterOut = IERC20(step.tokenOut).balanceOf(address(this));
            uint256 outDelta = afterOut - beforeOut;

            if (outDelta < step.minAmountOut) {
                emit ArbRevertedReason(routeId, "leg_min_out_not_met");
                revert InsufficientOutput(outDelta, step.minAmountOut);
            }

            currentToken = step.tokenOut;
            currentAmount = outDelta;
        }

        if (currentToken != startToken) {
            emit ArbRevertedReason(routeId, "final_token_mismatch");
            revert FinalTokenMismatch();
        }

        finalAmount = currentAmount;
        profit = finalAmount > initialAmount ? finalAmount - initialAmount : 0;

        if (finalAmount < minAmountOutFinal || profit < minProfitAbsolute) {
            emit ArbRevertedReason(routeId, "min_profit_not_met");
            revert MinProfitNotMet(finalAmount, minAmountOutFinal, profit, minProfitAbsolute);
        }

        _safeTransfer(startToken, msg.sender, finalAmount);

        emit ArbExecuted(routeId, startToken, initialAmount, finalAmount, profit, gasStart - gasleft(), correlationId);
    }

    function _safeTransferFrom(address token, address from, address to, uint256 amount) internal {
        (bool ok, bytes memory data) = token.call(abi.encodeWithSelector(IERC20.transferFrom.selector, from, to, amount));
        require(ok && (data.length == 0 || abi.decode(data, (bool))), "transferFrom failed");
    }

    function _safeTransfer(address token, address to, uint256 amount) internal {
        (bool ok, bytes memory data) = token.call(abi.encodeWithSelector(IERC20.transfer.selector, to, amount));
        require(ok && (data.length == 0 || abi.decode(data, (bool))), "transfer failed");
    }

    function _safeApprove(address token, address spender, uint256 amount) internal {
        (bool ok0, bytes memory data0) = token.call(abi.encodeWithSelector(IERC20.approve.selector, spender, 0));
        require(ok0 && (data0.length == 0 || abi.decode(data0, (bool))), "approve reset failed");

        (bool ok, bytes memory data) = token.call(abi.encodeWithSelector(IERC20.approve.selector, spender, amount));
        require(ok && (data.length == 0 || abi.decode(data, (bool))), "approve failed");
    }
}
