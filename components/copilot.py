# =========================================================================
# LIVE WHO-STANDARD ENTOMOLOGY AI KNOWLEDGE COPILOT (components/copilot.py)
# =========================================================================
import os

import streamlit as st
from google import genai
from google.genai import types


def get_live_copilot_response(user_query: str) -> str:
    """
    Connects to the modern Gemini API using the new google-genai SDK
    with native Google Search Grounding safely mapped.
    """
    # Pull the API key securely from Streamlit secrets or system environment
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return (
            "⚠️ **API Key Configuration Required**\n\n"
            "To enable live web-crawling analytics, you must provide a valid Gemini API key.\n\n"
            "**How to fix this:**\n"
            "1. Create a folder named `.streamlit` in your root project directory.\n"
            "2. Create a file inside it called `secrets.toml`.\n"
            "3. Add your key exactly like this:\n"
            "```toml\n"
            "GEMINI_API_KEY = \"your_actual_api_key_here\"\n"
            "```"
        )

    try:
        # Initialize the modern standard GenAI client
        client = genai.Client(api_key=api_key)

        # Define the search grounding tool utilizing the explicit SDK types
        search_tool = types.Tool(google_search=types.GoogleSearch())

        # Build the configuration block with the system persona instructions
        config = types.GenerateContentConfig(
            tools=[search_tool],
            system_instruction=(
                "You are a world-class WHO medical entomology expert and public health consultant "
                "deployed at the UNIMAID Vector Sentinel Hub. Your goal is to provide elite field advice.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "- You have access to live Google Search. Always use it to verify current WHO, CDC, "
                "and peer-reviewed journal entries (PubMed, standard vector databases) regarding "
                "IVM, IRS, LSM, Bti formulations, and invasive threats like Anopheles stephensi.\n"
                "- Cite or reference your sources naturally when providing real-time data.\n"
                "- Keep responses actionable, scientific, clear, and structured for field investigators."
            )
        )

        # Execute the query content generation pass
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_query,
            config=config
        )
        return response.text

    except Exception as e:
        return f" Entomological Core Error: Failed to establish live uplink stream. Details: {str(e)}"


def render_copilot_page():
    """Renders the stateful, live-connected conversational interface."""
    st.markdown(" WHO Vector Control AI Copilot (Live Web Grounding)")
    st.markdown("---")

    st.write(
        "This terminal is connected via API to live search engines. It dynamically evaluates online databases "
        "to answer technical queries regarding Integrated Vector Management (IVM), larviciding, and field operations."
    )

    # Initialize persistent stateful chat logs
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = [
            {"role": "assistant", "content": "Greetings Investigator. My live web-search links are online. Ask me any complex question regarding IVM frameworks, resistance variations, or localized field deployments."}
        ]

    # Render past conversation history clearly
    for message in st.session_state["chat_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Handle incoming user entries
    if user_input := st.chat_input("Ask about vector protocols (e.g., 'What are the current WHO recommended dosages for IRS?')"):
        # Append and display user input
        st.session_state["chat_messages"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Generate and render live assistant response block
        with st.chat_message("assistant"):
            with st.spinner("Executing live web search and synthesizing academic literature..."):
                response = get_live_copilot_response(user_input)
                st.markdown(response)

        st.session_state["chat_messages"].append({"role": "assistant", "content": response})
