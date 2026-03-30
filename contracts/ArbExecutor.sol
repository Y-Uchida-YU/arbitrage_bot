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

    struct RouteConfig {
        bool enabled;
        address startToken;
        address midToken;
        address[2] routers;
        bytes32[2] poolIds;
        uint24[2] feeTiers;
        bytes4[2] selectors;
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
    event RouteRegistered(bytes32 indexed routeId, bool enabled);
    event Paused(address indexed by);
    event Unpaused(address indexed by);

    address public owner;
    bool public paused;

    mapping(address => bool) public allowlistedRouters;
    mapping(address => bool) public allowlistedTokens;
    mapping(bytes32 => RouteConfig) public routes;

    uint256 private _status;
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;
    uint256 private constant _MAX_STEP_DATA_BYTES = 512;

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
    error RouteNotRegistered(bytes32 routeId);
    error RouteValidationFailed(bytes32 routeId, uint256 step);
    error SelectorNotAllowed(bytes32 routeId, uint256 step, bytes4 selector);
    error StepDataTooLarge(bytes32 routeId, uint256 step, uint256 length);

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

    constructor(address[] memory routers_, address[] memory tokens_) {
        owner = msg.sender;
        _status = _NOT_ENTERED;

        for (uint256 i = 0; i < routers_.length; i++) {
            allowlistedRouters[routers_[i]] = true;
        }
        for (uint256 i = 0; i < tokens_.length; i++) {
            allowlistedTokens[tokens_[i]] = true;
        }
    }

    function setAllowlistedRouter(address router, bool allowed) external onlyOwner {
        allowlistedRouters[router] = allowed;
    }

    function setAllowlistedToken(address token, bool allowed) external onlyOwner {
        allowlistedTokens[token] = allowed;
    }

    function registerRoute(
        bytes32 routeId,
        address startToken,
        address midToken,
        address[2] calldata routers_,
        bytes32[2] calldata poolIds,
        uint24[2] calldata feeTiers,
        bytes4[2] calldata selectors,
        bool enabled
    ) external onlyOwner {
        if (!allowlistedTokens[startToken]) revert NotAllowlistedToken(startToken);
        if (!allowlistedTokens[midToken]) revert NotAllowlistedToken(midToken);
        if (!allowlistedRouters[routers_[0]]) revert NotAllowlistedRouter(routers_[0]);
        if (!allowlistedRouters[routers_[1]]) revert NotAllowlistedRouter(routers_[1]);
        require(selectors[0] != bytes4(0) && selectors[1] != bytes4(0), "zero-selector");

        routes[routeId] = RouteConfig({
            enabled: enabled,
            startToken: startToken,
            midToken: midToken,
            routers: routers_,
            poolIds: poolIds,
            feeTiers: feeTiers,
            selectors: selectors
        });

        emit RouteRegistered(routeId, enabled);
    }

    function setRouteEnabled(bytes32 routeId, bool enabled) external onlyOwner {
        RouteConfig storage cfg = routes[routeId];
        if (cfg.startToken == address(0)) revert RouteNotRegistered(routeId);
        cfg.enabled = enabled;
        emit RouteRegistered(routeId, enabled);
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
        if (steps.length != 2) {
            emit ArbRevertedReason(routeId, "invalid_steps_len");
            revert InvalidPath();
        }
        if (!allowlistedTokens[startToken]) {
            emit ArbRevertedReason(routeId, "start_token_not_allowlisted");
            revert NotAllowlistedToken(startToken);
        }

        RouteConfig memory cfg = routes[routeId];
        if (cfg.startToken == address(0) || !cfg.enabled) {
            emit ArbRevertedReason(routeId, "route_not_registered");
            revert RouteNotRegistered(routeId);
        }
        if (cfg.startToken != startToken) {
            emit ArbRevertedReason(routeId, "route_start_mismatch");
            revert RouteValidationFailed(routeId, 0);
        }

        _validateStep(routeId, cfg, steps[0], 0);
        _validateStep(routeId, cfg, steps[1], 1);

        uint256 gasStart = gasleft();

        _safeTransferFrom(startToken, msg.sender, address(this), initialAmount);

        (address leg1Token, uint256 leg1Amount) = _executeStep(routeId, steps[0], 0, startToken, initialAmount);
        (address leg2Token, uint256 leg2Amount) = _executeStep(routeId, steps[1], 1, leg1Token, leg1Amount);

        if (leg2Token != startToken) {
            emit ArbRevertedReason(routeId, "final_token_mismatch");
            revert FinalTokenMismatch();
        }

        finalAmount = leg2Amount;
        profit = finalAmount > initialAmount ? finalAmount - initialAmount : 0;

        if (finalAmount < minAmountOutFinal || profit < minProfitAbsolute) {
            emit ArbRevertedReason(routeId, "min_profit_not_met");
            revert MinProfitNotMet(finalAmount, minAmountOutFinal, profit, minProfitAbsolute);
        }

        _safeTransfer(startToken, msg.sender, finalAmount);

        emit ArbExecuted(routeId, startToken, initialAmount, finalAmount, profit, gasStart - gasleft(), correlationId);
    }

    function _executeStep(
        bytes32 routeId,
        SwapStep calldata step,
        uint256 stepIndex,
        address expectedTokenIn,
        uint256 currentAmount
    ) internal returns (address nextToken, uint256 nextAmount) {
        if (step.data.length > _MAX_STEP_DATA_BYTES) {
            revert StepDataTooLarge(routeId, stepIndex, step.data.length);
        }

        if (!allowlistedRouters[step.router]) {
            emit ArbRevertedReason(routeId, "router_not_allowlisted");
            revert NotAllowlistedRouter(step.router);
        }
        if (!allowlistedTokens[step.tokenIn] || !allowlistedTokens[step.tokenOut]) {
            emit ArbRevertedReason(routeId, "token_not_allowlisted");
            revert NotAllowlistedToken(!allowlistedTokens[step.tokenIn] ? step.tokenIn : step.tokenOut);
        }
        if (step.tokenIn != expectedTokenIn) {
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

        return (step.tokenOut, outDelta);
    }

    function _validateStep(bytes32 routeId, RouteConfig memory cfg, SwapStep calldata step, uint256 index) internal pure {
        address expectedRouter = cfg.routers[index];
        bytes32 expectedPoolId = cfg.poolIds[index];
        uint24 expectedFeeTier = cfg.feeTiers[index];
        bytes4 expectedSelector = cfg.selectors[index];

        address expectedTokenIn = index == 0 ? cfg.startToken : cfg.midToken;
        address expectedTokenOut = index == 0 ? cfg.midToken : cfg.startToken;

        if (
            step.router != expectedRouter ||
            step.tokenIn != expectedTokenIn ||
            step.tokenOut != expectedTokenOut ||
            step.poolId != expectedPoolId ||
            step.feeTier != expectedFeeTier
        ) {
            revert RouteValidationFailed(routeId, index);
        }

        bytes4 selector = _selector(step.data);
        if (selector != expectedSelector) {
            revert SelectorNotAllowed(routeId, index, selector);
        }
    }

    function _selector(bytes calldata data) internal pure returns (bytes4 sel) {
        require(data.length >= 4, "bad-data");
        assembly {
            sel := calldataload(data.offset)
        }
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
