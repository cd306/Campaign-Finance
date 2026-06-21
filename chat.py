import json
import os
import sys

import anthropic
from dotenv import load_dotenv

import fec

load_dotenv()

client = anthropic.Anthropic()

SYSTEM_PROMPT = """You are a campaign finance research assistant for a journalist covering federal elections.

You have access to real-time data from the FEC (Federal Election Commission) via tools. Always use tools to retrieve actual data before answering — never estimate, guess, or fabricate figures.

## Tool use rules (follow strictly to avoid API rate limits)

For industry/employer questions (e.g. "how much from defense?", "what industries fund this candidate?"):
1. Call search_candidate once to get the committee ID.
2. Call get_employer_breakdown ONCE to get all employers and their totals in a single request.
3. Filter and sum the results yourself — do NOT call get_contributions or get_employer_breakdown repeatedly for each employer. One call returns all the data you need.

For donor detail questions (e.g. "who are the biggest individual donors?", "show me contributions over $5k"):
- Use get_large_contributions or get_contributions with filters.

For employer name searches (e.g. "show all Raytheon contributions"):
- Use get_contributions with the employer parameter.

For PAC contribution questions (e.g. "what PACs gave to this candidate?", "how much PAC money from defense?"):
- Use get_pac_contributions ONCE to get all PACs aggregated by name.
- Identify industry-affiliated PACs from their names (e.g. "Raytheon PAC", "National Association of Realtors PAC", "EMILY's List").
- Do NOT call get_contributions separately for each PAC.

## Content guidelines
- When interpreting an industry, identify relevant employer names from the get_employer_breakdown results. For example, "defense" maps to employers like Raytheon, Lockheed Martin, General Dynamics, Northrop Grumman, Boeing, L3Harris, BAE Systems, SAIC, General Atomics, Leidos, etc.
- Cite specific employers, amounts, and donor counts — not just totals.
- Flag contributions from PACs, LLCs, victory funds, or corporations vs. individual donors.
- If a candidate has multiple committees, focus on their principal campaign committee unless asked otherwise.
- Note that this tool covers federal candidates only (House, Senate, President). California state legislators are not in FEC data.
- Be concise and journalistically useful — lead with the headline number, then break it down."""

TOOLS = [
    {
        "name": "search_candidate",
        "description": "Search for a federal candidate by name. Returns their FEC committee ID(s), office, state, and district. Always call this first before looking up contribution data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Candidate's name (partial names work, e.g. 'Scott Peters')"},
                "state": {"type": "string", "description": "Two-letter state abbreviation, e.g. 'CA'"},
                "office": {"type": "string", "description": "Office type: 'House', 'Senate', or 'President'"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_employer_breakdown",
        "description": "Get contributions to a candidate aggregated by employer, sorted by total amount. Use this to answer questions about industries or employer groups.",
        "input_schema": {
            "type": "object",
            "properties": {
                "committee_id": {"type": "string", "description": "FEC committee ID, e.g. 'C00503110'"},
                "cycle": {"type": "integer", "description": "Election cycle year, e.g. 2024 or 2026"},
                "limit": {"type": "integer", "description": "Number of employers to return (default 30, max 100)"},
            },
            "required": ["committee_id", "cycle"],
        },
    },
    {
        "name": "get_contributions",
        "description": "Get itemized individual contributions to a candidate with optional filters. Use this to see specific donors, filter by employer name, or get a full donor list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "committee_id": {"type": "string", "description": "FEC committee ID"},
                "cycle": {"type": "integer", "description": "Election cycle year"},
                "min_amount": {"type": "number", "description": "Minimum contribution amount in dollars"},
                "employer": {"type": "string", "description": "Filter by employer name (partial match)"},
                "limit": {"type": "integer", "description": "Number of contributions to return (default 50)"},
            },
            "required": ["committee_id", "cycle"],
        },
    },
    {
        "name": "get_pac_contributions",
        "description": "Get all PAC contributions to a candidate, aggregated by PAC name and sorted by total. Use this for any question about PAC money, corporate PACs, industry PACs, or the split between PAC and individual donors.",
        "input_schema": {
            "type": "object",
            "properties": {
                "committee_id": {"type": "string", "description": "FEC committee ID"},
                "cycle": {"type": "integer", "description": "Election cycle year"},
                "limit": {"type": "integer", "description": "Max PAC contributions to fetch before aggregating (default 100)"},
            },
            "required": ["committee_id", "cycle"],
        },
    },
    {
        "name": "get_large_contributions",
        "description": "Get contributions above a dollar threshold, sorted by amount descending. Useful for finding major donors or near-limit contributions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "committee_id": {"type": "string", "description": "FEC committee ID"},
                "cycle": {"type": "integer", "description": "Election cycle year"},
                "threshold": {"type": "number", "description": "Minimum amount in dollars (default $5,000)"},
            },
            "required": ["committee_id", "cycle"],
        },
    },
]


def dispatch(tool_name: str, tool_input: dict):
    if tool_name == "search_candidate":
        return fec.search_candidate(**tool_input)
    elif tool_name == "get_employer_breakdown":
        return fec.get_employer_breakdown(**tool_input)
    elif tool_name == "get_contributions":
        return fec.get_contributions(**tool_input)
    elif tool_name == "get_pac_contributions":
        return fec.get_pac_contributions(**tool_input)
    elif tool_name == "get_large_contributions":
        return fec.get_large_contributions(**tool_input)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


def run():
    messages = []
    print("Campaign Finance Research Assistant")
    print("Federal candidates only (FEC data). Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            sys.exit(0)

        messages.append({"role": "user", "content": user_input})

        # Agentic loop: keep going until Claude stops requesting tools
        while True:
            response = client.messages.create(
                model="claude-opus-4-7",
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOLS,
                max_tokens=4096,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        print(f"\nAssistant: {block.text}\n")
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"  [calling {block.name}...]", flush=True)
                        result = dispatch(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        })
                messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    run()
