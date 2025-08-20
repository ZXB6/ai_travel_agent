from textwrap import dedent
from agno.agent import Agent
from agno.models.google import Gemini
from agno.tools.serpapi import SerpApiTools
import streamlit as st
import re
from agno.models.openai import OpenAIChat
from icalendar import Calendar, Event
from datetime import datetime, timedelta


def generate_ics_content(plan_text:str, start_date: datetime = None) -> bytes:
    """
        Generate an ICS calendar file from a travel itinerary text.

        Args:
            plan_text: The travel itinerary text
            start_date: Optional start date for the itinerary (defaults to today)

        Returns:
            bytes: The ICS file content as bytes
        """
    cal = Calendar()
    cal.add('prodid','-//AI Travel Planner//github.com//' )
    cal.add('version', '2.0')

    if start_date is None:
        start_date = datetime.today()

    # Split the plan into days
    day_pattern = re.compile(r'Day (\d+)[:\s]+(.*?)(?=Day \d+|$)', re.DOTALL)
    days = day_pattern.findall(plan_text)

    if not days: # If no day pattern found, create a single all-day event with the entire content
        event = Event()
        event.add('summary', "旅行行程")
        event.add('description', plan_text)
        event.add('dtstart', start_date.date())
        event.add('dtend', start_date.date())
        event.add("dtstamp", datetime.now())
        cal.add_component(event)  
    else:
        # Process each day
        for day_num, day_content in days:
            day_num = int(day_num)
            current_date = start_date + timedelta(days=day_num - 1)
            
            # Create a single event for the entire day
            event = Event()
            event.add('summary', f"第 {day_num} 天行程")
            event.add('description', day_content.strip())
            
            # Make it an all-day event
            event.add('dtstart', current_date.date())
            event.add('dtend', current_date.date())
            event.add("dtstamp", datetime.now())
            cal.add_component(event)

    return cal.to_ical()

# Set up the Streamlit app
st.title("AI 旅行计划助手")
st.caption("使用 AI 旅行计划助手，通过 GPT-4o 自动研究和规划个性化行程，计划您的下一次冒险")

# Initialize session state to store the generated itinerary
if 'itinerary' not in st.session_state:
    st.session_state.itinerary = None

# Get OpenAI API key from user
openai_api_key = st.text_input("输入 OpenAI API 密钥以访问 GPT-4o", type="password")

# Get SerpAPI key from the user
serp_api_key = st.text_input("输入 Serp API 密钥以使用搜索功能", type="password")

if openai_api_key and serp_api_key:
    researcher = Agent(
        name="研究员",
        role="根据用户偏好搜索旅游目的地、活动和住宿",
        model = Gemini(id="gemini-2.0-flash-exp", api_key=openai_api_key),
        description=dedent(
            """            你是一位世界级的旅行研究员。根据用户想去的旅行目的地和旅行天数，
            生成一个搜索词列表，用于查找相关的旅行活动和住宿。
            然后，为每个词条搜索网络，分析结果，并返回10个最相关的结果。
        """
        ),
        instructions=[
            "根据用户想去的旅行目的地和旅行天数，首先生成一个包含3个与该目的地和天数相关的搜索词的列表。",
            "对每个搜索词执行 `search_google` 并分析结果。",
            "从所有搜索结果中，返回与用户偏好最相关的10个结果。",
            "请记住：结果的质量很重要。",
            "请用中文回复。",
        ],
        tools=[SerpApiTools(api_key=serp_api_key)],
        add_datetime_to_instructions=True,
    )
    planner = Agent(
        name="规划师",
        role="根据用户偏好和研究结果生成行程草案",
        model=Gemini(id="gemini-2.0-flash-exp", api_key=openai_api_key),
        description=dedent(
            """            你是一位高级旅行规划师。根据用户想去的旅行目的地、
            旅行天数以及一份研究结果列表，你的目标是生成一份满足用户需求和偏好的行程草案。
        """
        ),
        instructions=[
            "根据用户想去的旅行目的地、旅行天数以及一份研究结果列表，生成一份包含建议活动和住宿的行程草案。",
            "确保行程结构合理、内容丰富且引人入胜。",
            "确保你提供一个细致入微且均衡的行程，尽可能引用事实。",
            "请记住：行程的质量很重要。",
            "注重清晰度、连贯性和整体质量。",
            "绝不捏造事实或抄袭。始终提供正确的署名。",
            "请用中文回复。",
        ],
        add_datetime_to_instructions=True,
    )

    # Input fields for the user's destination and the number of days they want to travel for
    destination = st.text_input("你想去哪里？")
    num_days = st.number_input("你计划旅行多少天？", min_value=1, max_value=30, value=7)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("生成行程"):
            with st.spinner("正在研究您的目的地..."):
                # First get research results
                research_results = researcher.run(f"为一次为期 {num_days} 天的旅行研究 {destination}", stream=False)

                # Show research progress
                st.write("研究完成")
                
            with st.spinner("正在创建您的个性化行程..."):
                # Pass research results to planner
                prompt = f"""
                目的地: {destination}
                时长: {num_days} 天
                研究结果: {research_results.content}
                
                请根据这项研究创建一个详细的行程。
                """
                response = planner.run(prompt, stream=False)
                # Store the response in session state
                st.session_state.itinerary = response.content
                st.write(response.content)
    
    # Only show download button if there's an itinerary
    with col2:
        if st.session_state.itinerary:
            # Generate the ICS file
            ics_content = generate_ics_content(st.session_state.itinerary)
            
            # Provide the file for download
            st.download_button(
                label="下载行程为日历文件 (.ics)",
                data=ics_content,
                file_name="travel_itinerary.ics",
                mime="text/calendar"

            )
