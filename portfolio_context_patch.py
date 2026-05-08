"""
portfolio_context_patch.py

Injects the live portfolio position (cash, SPY shares, interest earned)
into the Portfolio Manager's prompt each cycle.

How it works:
- Monkey-patches create_portfolio_manager in the tradingagents package.
- Wraps the LLM passed to that function with a thin class that prepends
  the current portfolio state to every prompt at call time.
- The portfolio object is read by reference, so values are always current.

Usage (call once before build_graph):
    from portfolio_context_patch import apply_portfolio_context_patch
    apply_portfolio_context_patch(portfolio)
"""


class _PortfolioAwareLLM:
    """
    Thin LLM wrapper that prepends current portfolio state to every prompt
    before forwarding the call to the real LLM.
    """

    def __init__(self, llm, portfolio):
        self._llm = llm
        self._portfolio = portfolio

    def __getattr__(self, name):
        return getattr(self._llm, name)

    def _position_block(self) -> str:
        p = self._portfolio
        spy_value = ""
        if p.shares > 0:
            spy_value = f" (cost basis ${p.cost_basis:,.2f}/share)"
        return (
            "**Current Portfolio Position:**\n"
            f"- Cash available       : ${p.cash:,.2f}\n"
            f"- SPY shares held      : {p.shares:,.4f}{spy_value}\n"
            f"- Interest earned (YTD): ${p.interest_earned:,.2f}\n"
        )

    def invoke(self, prompt, **kwargs):
        if isinstance(prompt, str):
            prompt = self._position_block() + "\n---\n\n" + prompt
        return self._llm.invoke(prompt, **kwargs)


def apply_portfolio_context_patch(portfolio) -> None:
    """
    Monkey-patch create_portfolio_manager so the Portfolio Manager agent
    receives the live portfolio position in its prompt every cycle.

    Call once before TradingAgentsGraph is constructed.
    """
    import tradingagents.agents.managers.portfolio_manager as pm_module

    original_create = pm_module.create_portfolio_manager

    def patched_create(llm, memory):
        wrapped_llm = _PortfolioAwareLLM(llm, portfolio)
        return original_create(wrapped_llm, memory)

    pm_module.create_portfolio_manager = patched_create
