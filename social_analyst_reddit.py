"""
Replacement social media analyst that combines Reddit posts (real crowd sentiment)
with the standard news feed.

Usage — patch tradingagents before creating TradingAgentsGraph:

    import tradingagents.graph.setup as ta_setup
    from social_analyst_reddit import create_social_media_analyst_with_reddit
    ta_setup.create_social_media_analyst = create_social_media_analyst_with_reddit

This replaces the function in the already-imported module namespace so the graph
picks up our version without any changes to the tradingagents source code.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
)
from tradingagents.dataflows.config import get_config
from reddit_tool import get_reddit_sentiment


def create_social_media_analyst_with_reddit(llm):
    """
    Drop-in replacement for tradingagents' create_social_media_analyst.
    Adds get_reddit_sentiment alongside the existing get_news tool.
    """
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_news, get_reddit_sentiment]

        system_message = (
            "You are a social media and sentiment analyst. Your job is to gauge "
            "real retail investor sentiment around SPY using two data sources:\n"
            "1. Reddit posts from r/wallstreetbets, r/investing, r/SPY, r/stocks, "
            "and r/options via get_reddit_sentiment — this gives you raw crowd "
            "sentiment: post scores, upvote ratios, top comments, and engagement.\n"
            "2. Financial news via get_news — this gives you institutional and "
            "media-driven sentiment.\n\n"
            "Use BOTH tools. Write a comprehensive report covering:\n"
            "- Overall retail sentiment tone (bullish / neutral / bearish) with "
            "evidence from Reddit scores and upvote ratios.\n"
            "- Key themes and narratives being discussed (e.g. macro fears, earnings "
            "expectations, options flow mentions, geopolitical concerns).\n"
            "- Any divergence between retail Reddit sentiment and news-driven sentiment.\n"
            "- Specific high-engagement posts or comments that signal conviction.\n"
            "Conclude with a Markdown table summarising the key sentiment signals."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant "
                    "with different tools will help where you left off. Execute what you "
                    "can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: "
                    "**BUY/HOLD/SELL** or deliverable, prefix your response with "
                    "FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows "
                    "to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    " For your reference, the current date is {current_date}. "
                    "{instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([t.name for t in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "sentiment_report": report,
        }

    return social_media_analyst_node


def apply_reddit_patch():
    """
    Call this once before instantiating TradingAgentsGraph to activate
    the Reddit-enhanced social analyst.
    """
    import tradingagents.graph.setup as ta_setup
    ta_setup.create_social_media_analyst = create_social_media_analyst_with_reddit
