import asyncio
from tools.search_tool import tavily_search

# 1. Keep it as a normal async function for debugging
async def debug_tavily() -> None:
    response = await tavily_search.search(
        "University of Manchester Computer Science undergraduate",
        max_results=3,
    )
    # 🛑 SET YOUR BREAKPOINT HERE
    print(response.query)


if __name__ == "__main__":
    # 2. Run it directly
    asyncio.run(debug_tavily())