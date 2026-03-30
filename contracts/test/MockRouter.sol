// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20Lite {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

contract MockRouter {
    bool public shouldRevert;

    function setShouldRevert(bool v) external {
        shouldRevert = v;
    }

    function swap(address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut) external {
        require(!shouldRevert, "forced-revert");
        IERC20Lite(tokenIn).transferFrom(msg.sender, address(this), amountIn);
        IERC20Lite(tokenOut).transfer(msg.sender, amountOut);
    }
}