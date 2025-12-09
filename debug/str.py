import streamlit as st
import json
import sys
from datetime import datetime
from typing import Optional
from io import StringIO
import contextlib

# Import your actual modules
from intent_classifier import get_intent_classifier
from semantic_parser import build_semantic_parse
from db_interface import process_semantic_query, inject_db_results, needs_fuzzy_search
from chatalogue import (
    ConversationContext,
    call_external_db_service,
    format_db_results_for_rag,
    rag_answer_with_db,
)

st.set_page_config(page_title="Chatalogue Debug Pipeline", layout="wide")

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 30px;
    }
    .intent-box {
        background-color: #e7f3ff;
        border-left: 5px solid #2196F3;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .semantic-box {
        background-color: #fff3e0;
        border-left: 5px solid #ff9800;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .context-box {
        background-color: #f1f8e9;
        border-left: 5px solid #4caf50;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .fuzzy-box {
        background-color: #fce4ec;
        border-left: 5px solid #e91e63;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .sql-box {
        background-color: #f3e5f5;
        border-left: 5px solid #9c27b0;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .db-box {
        background-color: #e0f2f1;
        border-left: 5px solid #009688;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .rag-box {
        background-color: #fff9c4;
        border-left: 5px solid #ffc107;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .llm-box {
        background-color: #e8eaf6;
        border-left: 5px solid #3f51b5;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .entity-badge {
        display: inline-block;
        background-color: #667eea;
        color: white;
        padding: 5px 10px;
        border-radius: 15px;
        margin: 5px;
        font-size: 14px;
    }
    .success-badge {
        background-color: #4caf50;
    }
    .info-badge {
        background-color: #2196F3;
    }
    .chat-message {
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 15px;
    }
    .user-message {
        background-color: #000000;
        border-left: 4px solid #2196F3;
    }
    .assistant-message {
        background-color: #000000;
        border-left: 4px solid #4caf50;
    }
    .timestamp {
        font-size: 12px;
        color: #666;
        margin-top: 5px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>🔍 CHATALOGUE DEBUG PIPELINE</h1></div>', unsafe_allow_html=True)

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

if 'context' not in st.session_state:
    st.session_state.context = ConversationContext()

if 'debug_data' not in st.session_state:
    st.session_state.debug_data = None

def run_debug_pipeline(user_input: str, ctx: ConversationContext):
    """Run the complete debug pipeline and capture all data"""
    debug_info = {
        'user_input': user_input,
        'context_str': ctx.compress(),
    }
    
    # Stage 1: Intent Classification
    clf = get_intent_classifier()
    intent_result = clf.classify_intent(user_input)
    debug_info['intent'] = {
        'primary_intent': intent_result["primary_intent"],
        'confidence': intent_result['confidence'] * 100,
        'top_k': [(k, v * 100) for k, v in intent_result["top_k"]],
        'raw': intent_result
    }
    
    # Stage 2: Semantic Parsing
    semantic = build_semantic_parse(user_input, ctx)
    debug_info['semantic'] = {
        'course_codes': semantic.get("course_codes", []),
        'instructor_names': semantic.get("instructor_names", []),
        'weekdays': semantic.get("weekdays", []),
        'course_name_queries': semantic.get("course_name_queries", []),
        'requested_attributes': semantic.get("requested_attributes", []),
        'primary_intent': semantic.get("primary_intent"),
        'primary_confidence': semantic.get('primary_confidence', 0) * 100,
        'is_multi_query': semantic.get("is_multi_query"),
        'subqueries': semantic.get("subqueries", [])
    }
    
    # Stage 3: Context Handling
    context_before = {
        'active_course': ctx.active_course,
        'active_instructor': ctx.active_instructor,
        'active_weekdays': ctx.active_weekdays,
        'turn_count': ctx.turn_count
    }
    
    should_reset = ctx.should_reset_context(user_input, semantic)
    if should_reset:
        ctx.reset()
    
    semantic = ctx.resolve_pronouns(semantic, user_input)
    
    debug_info['context'] = {
        'before': context_before,
        'should_reset': should_reset,
        'after_pronouns': {
            'course_codes': semantic.get("course_codes", []),
            'instructor_names': semantic.get("instructor_names", []),
            'weekdays': semantic.get("weekdays", [])
        }
    }
    
    # Stage 4: Fuzzy Search
    needs_fuzzy = needs_fuzzy_search(semantic)
    debug_info['fuzzy'] = {
        'needs_fuzzy': needs_fuzzy,
        'results': []
    }
    
    if needs_fuzzy:
        course_name_queries = semantic.get("course_name_queries", [])
        accumulated_course_codes = []
        
        for course_name in course_name_queries:
            fuzzy_request = {
                "query_type": "fuzzy_course_search",
                "search_term": course_name
            }
            fuzzy_results = call_external_db_service(fuzzy_request)
            
            if fuzzy_results:
                for result in fuzzy_results:
                    code = result.get('course_number')
                    if code and code not in accumulated_course_codes:
                        accumulated_course_codes.append(code)
                debug_info['fuzzy']['results'].append({
                    'search_term': course_name,
                    'count': len(fuzzy_results),
                    'courses': fuzzy_results[:10]
                })
        
        if accumulated_course_codes:
            semantic['course_codes'] = accumulated_course_codes
    
    # Stage 5: SQL Query Generation
    query_request = process_semantic_query(semantic)
    debug_info['sql'] = {
        'query_request': query_request,
        'subqueries': query_request.get('subqueries', [])
    }
    
    # Stage 6: Database Execution
    db_rows = call_external_db_service(query_request)
    db_result = inject_db_results(query_request, db_rows)
    
    debug_info['db'] = {
        'raw_rows': db_rows,
        'structured': db_result,
        'total_rows': sum(len(subres.get("rows", [])) for subres in db_result.get("subresults", []))
    }
    
    # Stage 7: Context Update
    context_before_update = {
        'active_course': ctx.active_course,
        'active_instructor': ctx.active_instructor,
        'active_weekdays': ctx.active_weekdays
    }
    
    ctx.update(semantic, db_result, user_input)
    
    context_after_update = {
        'active_course': ctx.active_course,
        'active_instructor': ctx.active_instructor,
        'active_weekdays': ctx.active_weekdays,
        'turn_count': ctx.turn_count,
        'known_facts': list(ctx.known_facts.keys())[:5] if ctx.known_facts else []
    }
    
    debug_info['context_update'] = {
        'before': context_before_update,
        'after': context_after_update
    }
    
    # Stage 8: RAG Prompt Construction
    db_text = format_db_results_for_rag(db_result)
    debug_info['rag'] = {
        'db_text': db_text,
        'length': len(db_text)
    }
    
    # Stage 9: LLM Response
    try:
        answer = rag_answer_with_db(user_input, ctx, semantic, db_result)
        debug_info['llm'] = {
            'answer': answer,
            'error': None
        }
    except Exception as e:
        answer = f"Error: {str(e)}"
        debug_info['llm'] = {
            'answer': answer,
            'error': str(e)
        }
    
    return answer, debug_info

# Chat interface
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("💬 Query Interface")
    
    chat_container = st.container()
    
    with chat_container:
        for message in st.session_state.chat_history:
            if message['role'] == 'user':
                st.markdown(f"""
                <div class="chat-message user-message">
                    <strong>👤 You:</strong> {message['content']}
                    <div class="timestamp">{message['timestamp']}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-message assistant-message">
                    <strong>🤖 Assistant:</strong> {message['content']}
                    <div class="timestamp">{message['timestamp']}</div>
                </div>
                """, unsafe_allow_html=True)
    
    query_input = st.text_input("Type your query here:", key="query_input", placeholder="e.g., who teaches cs 575?")
    
    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns([1, 1, 1, 3])
    
    with col_btn1:
        send_button = st.button("🚀 Send", type="primary", use_container_width=True)
    
    with col_btn2:
        reset_button = st.button("🔄 Reset", use_container_width=True)
    
    with col_btn3:
        clear_chat = st.button("🗑️ Clear", use_container_width=True)
    
    if send_button and query_input:
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        st.session_state.chat_history.append({
            'role': 'user',
            'content': query_input,
            'timestamp': timestamp
        })
        
        with st.spinner("Processing..."):
            answer, debug_data = run_debug_pipeline(query_input, st.session_state.context)
            st.session_state.debug_data = debug_data
        
        st.session_state.chat_history.append({
            'role': 'assistant',
            'content': answer,
            'timestamp': timestamp
        })
        
        st.rerun()
    
    if reset_button:
        st.session_state.context.reset()
        st.success("Context reset!")
        st.rerun()
    
    if clear_chat:
        st.session_state.chat_history = []
        st.session_state.context = ConversationContext()
        st.session_state.debug_data = None
        st.rerun()

with col2:
    st.subheader("📊 Quick Stats")
    if st.session_state.debug_data:
        data = st.session_state.debug_data
        st.metric("Intent Confidence", f"{data['intent']['confidence']:.2f}%")
        st.metric("DB Rows", data['db']['total_rows'])
        st.metric("Turn Count", st.session_state.context.turn_count)
        st.metric("Messages", len(st.session_state.chat_history))
    else:
        st.info("Send a query to see stats")

# Debug pipeline visualization
if st.session_state.debug_data:
    st.divider()
    
    data = st.session_state.debug_data
    
    tab1, tab2 = st.tabs(["🎯 Pipeline Flow", "📋 Raw Data"])
    
    with tab1:
        # User Input
        st.info(f"**User Input:** {data['user_input']}")
        st.caption(f"**Context:** {data['context_str']}")
        
        # Stage 1: Intent Classification
        st.markdown('<div class="intent-box">', unsafe_allow_html=True)
        st.subheader("🎯 STAGE 1: Intent Classification")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"### Primary Intent: `{data['intent']['primary_intent']}`")
            st.progress(data['intent']['confidence'] / 100)
            st.caption(f"Confidence: {data['intent']['confidence']:.2f}%")
        
        with col2:
            st.markdown("**Top 3 Intents:**")
            for intent, conf in data['intent']['top_k']:
                st.markdown(f"<span class='entity-badge info-badge'>{intent}: {conf:.2f}%</span>", unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Stage 2: Semantic Parsing
        st.markdown('<div class="semantic-box">', unsafe_allow_html=True)
        st.subheader("🔍 STAGE 2: Semantic Parsing")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("**Course Codes:**")
            if data['semantic']['course_codes']:
                for code in data['semantic']['course_codes']:
                    st.markdown(f"<span class='entity-badge success-badge'>{code}</span>", unsafe_allow_html=True)
            else:
                st.caption("None")
        
        with col2:
            st.markdown("**Instructors:**")
            if data['semantic']['instructor_names']:
                for inst in data['semantic']['instructor_names']:
                    st.markdown(f"<span class='entity-badge success-badge'>{inst}</span>", unsafe_allow_html=True)
            else:
                st.caption("None")
        
        with col3:
            st.markdown("**Weekdays:**")
            if data['semantic']['weekdays']:
                for day in data['semantic']['weekdays']:
                    st.markdown(f"<span class='entity-badge success-badge'>{day}</span>", unsafe_allow_html=True)
            else:
                st.caption("None")
        
        with col4:
            st.markdown("**Requested Attributes:**")
            if data['semantic']['requested_attributes']:
                for attr in data['semantic']['requested_attributes']:
                    st.markdown(f"<span class='entity-badge info-badge'>{attr}</span>", unsafe_allow_html=True)
            else:
                st.caption("None")
        
        st.divider()
        st.markdown(f"**Multi-Query:** {'Yes' if data['semantic']['is_multi_query'] else 'No'}")
        
        if data['semantic']['subqueries']:
            st.markdown("**Subqueries:**")
            for i, subq in enumerate(data['semantic']['subqueries']):
                with st.expander(f"Subquery {i}: {subq.get('text', 'N/A')[:50]}..."):
                    st.json(subq)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Stage 3: Context Handling
        st.markdown('<div class="context-box">', unsafe_allow_html=True)
        st.subheader("🔄 STAGE 3: Context Handling")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Before Context Update:**")
            st.json(data['context']['before'])
        
        with col2:
            st.markdown("**After Pronoun Resolution:**")
            st.json(data['context']['after_pronouns'])
        
        st.divider()
        
        if data['context']['should_reset']:
            st.warning("⚠️ Context was reset")
        else:
            st.success("✅ Context maintained")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Stage 4: Fuzzy Search
        st.markdown('<div class="fuzzy-box">', unsafe_allow_html=True)
        st.subheader("🔎 STAGE 4: Fuzzy Search Check")
        
        col1, col2 = st.columns([1, 3])
        with col1:
            if data['fuzzy']['needs_fuzzy']:
                st.error("**Needs Fuzzy Search:** Yes")
            else:
                st.success("**Needs Fuzzy Search:** No")
        
        with col2:
            if data['fuzzy']['needs_fuzzy'] and data['fuzzy']['results']:
                for result in data['fuzzy']['results']:
                    st.caption(f"Search: '{result['search_term']}' → {result['count']} matches")
                    if result['courses']:
                        for course in result['courses']:
                            st.caption(f"  • {course.get('course_number')}: {course.get('course_name')}")
            else:
                st.caption("Proceeding with direct query")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Stage 5: SQL Query Generation
        st.markdown('<div class="sql-box">', unsafe_allow_html=True)
        st.subheader("💾 STAGE 5: SQL Query Generation")
        
        if data['sql']['subqueries']:
            for i, subq in enumerate(data['sql']['subqueries']):
                st.markdown(f"**Subquery {i}:**")
                if subq.get('sql_string'):
                    st.code(subq['sql_string'], language='sql')
                    st.code(f"Parameters: {subq.get('sql_params', [])}", language='python')
                else:
                    st.caption("No SQL query (chitchat intent)")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Stage 6: Database Execution
        st.markdown('<div class="db-box">', unsafe_allow_html=True)
        st.subheader("🗄️ STAGE 6: Database Execution")
        
        st.markdown(f"**Total Rows:** {data['db']['total_rows']}")
        
        if data['db']['structured'].get('subresults'):
            for i, subres in enumerate(data['db']['structured']['subresults']):
                rows = subres.get('rows', [])
                if rows:
                    st.markdown(f"**Result Set {i}:** {len(rows)} row(s)")
                    st.dataframe(rows, use_container_width=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Stage 7: Context Update
        st.markdown('<div class="context-box">', unsafe_allow_html=True)
        st.subheader("🔄 STAGE 7: Context Update")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Before Update:**")
            st.json(data['context_update']['before'])
        
        with col2:
            st.markdown("**After Update:**")
            st.json(data['context_update']['after'])
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Stage 8: RAG Prompt Construction
        st.markdown('<div class="rag-box">', unsafe_allow_html=True)
        st.subheader("📝 STAGE 8: RAG Prompt Construction")
        
        st.markdown(f"**DB Context Length:** {data['rag']['length']} characters")
        
        st.text_area("Formatted DB Context for LLM:", data['rag']['db_text'], height=200)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Stage 9: LLM Response
        st.markdown('<div class="llm-box">', unsafe_allow_html=True)
        st.subheader("🤖 STAGE 9: LLM Response Generation")
        
        if data['llm']['error']:
            st.error(f"**Error:** {data['llm']['error']}")
        else:
            st.success(f"**Final Answer:** {data['llm']['answer']}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab2:
        st.subheader("📋 Complete Debug Data")
        st.json(data)