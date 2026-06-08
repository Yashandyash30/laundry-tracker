import streamlit as st
import streamlit.components.v1 as components
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import pytz
import requests
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# --- 1. SETUP FIREBASE ---
if not firebase_admin._apps:
    key_dict = dict(st.secrets["firebase"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

if 'active_action' not in st.session_state:
    st.session_state['active_action'] = None

# --- 2. CONFIGURATION ---
# Refresh every 30 seconds to check for status changes
if not st.session_state.get('active_action'):
    st_autorefresh(interval=30000, key="data_refresh")

IST = pytz.timezone('Asia/Kolkata')
MASTER_PIN = st.secrets["general"]["master_pin"]
BUFFER_MINUTES = 15

# TELEGRAM CONFIG
BOT_TOKEN = st.secrets["telegram"]["bot_token"]
CHAT_ID_KRITIKA = st.secrets["telegram"]["chat_id_kritika"]
CHAT_ID_ROHINI = st.secrets["telegram"]["chat_id_rohini"]

# --- 3. NOTIFICATION SYSTEMS ---

def send_telegram(message, hostel_name):
    """Sends a message to the Telegram Group"""
    try:
        chat_id = CHAT_ID_KRITIKA if hostel_name == "Kritika Hostel" else CHAT_ID_ROHINI
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": f"[{hostel_name}] {message}",
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

def trigger_browser_notification(title, body):
    """Triggers a local browser notification"""
    js_code = f"""
    <script>
        function sendNotification() {{
            var title = "{title}";
            var options = {{
                body: "{body}",
                icon: "https://cdn-icons-png.flaticon.com/512/2954/2954888.png",
                requireInteraction: true
            }};
            if (Notification.permission === "granted") {{
                new Notification(title, options);
            }}
        }}
        sendNotification();
    </script>
    """
    components.html(js_code, height=0, width=0)

def request_permission_button():
    components.html("""
    <script>
        function askPermission() {
            Notification.requestPermission().then(function(result) {
                console.log(result);
            });
        }
    </script>
    <div style="text-align: center; margin-bottom: 10px;">
        <button onclick="askPermission()" style="
            background-color: #FF4B4B; color: white; padding: 8px 16px; 
            border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">
            🔔 Enable Browser Alerts
        </button>
    </div>
    """, height=50)

# --- 4. HELPER FUNCTIONS ---
def get_current_time():
    return datetime.now(IST)

def format_time(dt):
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime("%I:%M %p")

def add_log(hostel, machine, user, designation, duration_mins):
    try:
        log_data = {
            "timestamp": get_current_time().isoformat(),
            "machine": machine,
            "user": user,
            "designation": designation,
            "duration_mins": duration_mins
        }
        db.collection(f"{hostel}_logs").add(log_data)
    except Exception as e:
        print(f"Log error: {e}")

# Initialize Session State for Change Detection
if 'machine_states' not in st.session_state:
    st.session_state['machine_states'] = {}

# --- 5. APP INTERFACE ---
st.set_page_config(page_title="Hostel Laundry", page_icon="🧺", layout="wide")

with st.sidebar:
    st.write("### 🧭 Navigation")
    page = st.radio("Go to:", ["Dashboard", "Usage Logs", "Announcements", "User Manual"], label_visibility="collapsed")
    st.write("---")

if page == "Announcements":
    st.markdown("<h2 style='margin-top: -50px; margin-bottom: -15px;'>📢 Announcements</h2>", unsafe_allow_html=True)
    st.write("<br>", unsafe_allow_html=True)
    
    with st.form("admin_auth"):
        auth_pin = st.text_input("Master PIN", type="password")
        auth_submit = st.form_submit_button("Enter")
        
    if auth_pin == MASTER_PIN:
        target_hostel = st.selectbox("Target Hostel", ["Kritika Hostel", "Rohini Hostel", "Both"])
        target_category = st.selectbox("Target Category", ["Laundry", "First Aid", "Pantry", "All Categories"])
        msg = st.text_area("Announcement Message")
        
        if st.button("Publish"):
            hostels = ["Kritika Hostel", "Rohini Hostel"] if target_hostel == "Both" else [target_hostel]
            categories = ["Laundry", "First Aid", "Pantry"] if target_category == "All Categories" else [target_category]
            
            for h in hostels:
                for c in categories:
                    db.collection("announcements").document(f"{h}_{c}").set({"message": msg, "timestamp": get_current_time().isoformat()})
            st.success("Published!")
            
        st.write("---")
        st.write("### Current Announcements")
        try:
            hostels = ["Kritika Hostel", "Rohini Hostel"]
            categories = ["Laundry", "First Aid", "Pantry"]
            
            any_exists = False
            for h in hostels:
                st.write(f"#### {h}")
                for c in categories:
                    doc_id = f"{h}_{c}"
                    doc = db.collection("announcements").document(doc_id).get()
                    
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.write(f"**{c}:** {doc.to_dict().get('message') if doc.exists else 'None'}")
                    with c2:
                        if doc.exists:
                            any_exists = True
                            if st.button(f"Clear", key=f"clear_{doc_id}", use_container_width=True):
                                db.collection("announcements").document(doc_id).delete()
                                st.rerun()
            
            st.write("<br>", unsafe_allow_html=True)
            if any_exists and st.button("Clear All Announcements"):
                for h in hostels:
                    for c in categories:
                        db.collection("announcements").document(f"{h}_{c}").delete()
                st.rerun()
        except Exception:
            pass
    elif auth_pin:
        st.error("Incorrect PIN")
    st.stop()

if page == "Usage Logs":
    st.markdown("<h2 style='margin-top: -50px; margin-bottom: -15px;'>📜 Usage Logs</h2>", unsafe_allow_html=True)
    st.write("<br>", unsafe_allow_html=True)
    
    log_hostel = st.radio("**Select Hostel to view logs:**", ["Kritika Hostel", "Rohini Hostel"], horizontal=True)
    log_category = st.radio("**Select Category:**", ["Laundry", "First Aid", "Pantry"], horizontal=True)
    limit_choice = st.selectbox("Show last N logs:", [50, 100, 500, "All"])
    
    if log_hostel and log_category:
        if log_category == "Laundry":
            hostel_col = "machines_kritika" if log_hostel == "Kritika Hostel" else "machines_rohini"
        elif log_category == "First Aid":
            hostel_col = "firstaid_kritika" if log_hostel == "Kritika Hostel" else "firstaid_rohini"
        elif log_category == "Pantry":
            hostel_col = "pantry_kritika" if log_hostel == "Kritika Hostel" else "pantry_rohini"
            
        try:
            if limit_choice == "All":
                logs_ref = db.collection(f"{hostel_col}_logs").order_by("timestamp", direction=firestore.Query.DESCENDING)
            else:
                logs_ref = db.collection(f"{hostel_col}_logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit_choice)
                
            logs = [doc.to_dict() for doc in logs_ref.stream()]
            if logs:
                formatted_logs = []
                for log in logs:
                    dt_obj = datetime.fromisoformat(log.get('timestamp', get_current_time().isoformat()))
                    if log_category == "Laundry":
                        formatted_logs.append({
                            "Date & Time": dt_obj.strftime("%Y-%m-%d %I:%M %p"),
                            "Machine": log.get("machine", ""),
                            "User": log.get("user", ""),
                            "Designation": log.get("designation", ""),
                            "Duration (mins)": log.get("duration_mins", "")
                        })
                    elif log_category == "First Aid":
                        formatted_logs.append({
                            "Date & Time": dt_obj.strftime("%Y-%m-%d %I:%M %p"),
                            "User": log.get("user", ""),
                            "Designation": log.get("designation", ""),
                            "Things Used": log.get("things_used", "")
                        })
                    elif log_category == "Pantry":
                        formatted_logs.append({
                            "Date & Time": dt_obj.strftime("%Y-%m-%d %I:%M %p"),
                            "User": log.get("user", ""),
                            "Designation": log.get("designation", ""),
                            "Comments": log.get("comments", ""),
                            "Duration (mins)": log.get("duration_mins", "")
                        })
                st.dataframe(formatted_logs, use_container_width=True, hide_index=True)
            else:
                st.info("No logs found for this category and hostel.")
        except Exception as e:
            st.error(f"Could not load logs: {e}")
    st.stop()

if page == "User Manual":
    try:
        with open("Hostel_Tracker_Manual.md", "r", encoding="utf-8") as f:
            manual_content = f.read()
        st.markdown(manual_content)
    except FileNotFoundError:
        st.error("Manual file not found.")
    st.stop()

st.markdown("<h3 style='margin-top: -50px; margin-bottom: -15px;'>🏢 ARIES Hostel Tracker</h3>", unsafe_allow_html=True)
st.caption("Live Status • Telegram Alerts • Browser Notifications")

selected_hostel = st.radio(
    "**📍 Select Your Hostel:**", 
    ["Kritika Hostel", "Rohini Hostel"], 
    index=None, 
    horizontal=True,
    key="hostel_selector"
)

selected_category = None
if selected_hostel:
    selected_category = st.radio(
        "**📂 Select Category:**",
        ["Laundry", "First Aid", "Pantry"],
        horizontal=True,
        key="category_selector"
    )

st.write("")

if not selected_hostel or not selected_category:
    st.info("👆 Please select your hostel and category above.")
    with st.sidebar:
        st.write("### ⚙️ Settings")
        request_permission_button()
    st.stop()

try:
    doc_id = f"{selected_hostel}_{selected_category}"
    announcement_doc = db.collection("announcements").document(doc_id).get()
    if announcement_doc.exists:
        ann_data = announcement_doc.to_dict()
        if ann_data and ann_data.get("message"):
            st.warning(f"📢 **{selected_category} Announcement:** {ann_data['message']}")
            
    # Fallback to check generic hostel announcement for backward compatibility
    gen_doc = db.collection("announcements").document(selected_hostel).get()
    if gen_doc.exists:
        gen_data = gen_doc.to_dict()
        if gen_data and gen_data.get("message"):
            st.warning(f"📢 **Hostel Announcement:** {gen_data['message']}")
except Exception:
    pass

with st.sidebar:
    st.success(f"📍 **Current:** {selected_hostel}")
    st.write("---")
    st.write("### ⚙️ Settings")
    request_permission_button()

if selected_category == "First Aid":
    st.markdown("## 🩹 First Aid Kit Log")
    st.write("Please log the items you have used from the First Aid Kit.")
    with st.form("first_aid_form"):
        fa_name = st.text_input("Name *")
        fa_desig = st.selectbox("Designation *", ["PhD", "PDF", "Project Student", "Visitor"])
        fa_used = st.text_area("Things Used (Comments) *", placeholder="e.g., Band-Aids, Antiseptic cream")
        
        fa_submit = st.form_submit_button("Log Usage", type="primary", use_container_width=True)
        
    if fa_submit:
        if not fa_name.strip() or not fa_used.strip():
            st.error("⚠️ Please fill in all mandatory fields (Name and Things Used).")
        else:
            hostel_col = "firstaid_kritika" if selected_hostel == "Kritika Hostel" else "firstaid_rohini"
            log_data = {
                "timestamp": get_current_time().isoformat(),
                "user": fa_name,
                "designation": fa_desig,
                "things_used": fa_used
            }
            db.collection(f"{hostel_col}_logs").add(log_data)
            st.success("✅ Logged successfully!")
            send_telegram(f"🩹 *First Aid Kit Used*\n👤 {fa_name}\n📝 Used: {fa_used}", selected_hostel)
    st.stop()

elif selected_category == "Pantry":
    st.markdown("## 🍳 Pantry Tracker")
    hostel_id = "pantry_kritika" if selected_hostel == "Kritika Hostel" else "pantry_rohini"
    doc_ref = db.collection("pantry").document(hostel_id)
    doc_snap = doc_ref.get()
    p_data = doc_snap.to_dict() if doc_snap.exists else {}
    
    current_user = p_data.get("current_user", None)
    queue = p_data.get("queue", [])
    last_free_time_str = p_data.get("last_free_time", None)

    # State: Join Queue
    if st.session_state.get('pantry_action') == 'Join Queue':
        st.markdown("### Join Pantry Queue")
        with st.container(border=True):
            q_name = st.text_input("Name *")
            q_desig = st.selectbox("Designation *", ["PhD", "PDF", "Project Student", "Visitor"])
            q_comment = st.text_input("Comment (Optional)", placeholder="e.g., Making tea")
            q_is_urgent = st.checkbox("🔥 Urgent?")
            q_reason = st.text_input("Reason") if q_is_urgent else ""
            q_pin = st.text_input("PIN *", type="password")
            
            c1, c2 = st.columns(2)
            with c1:
                submitted = st.button("Confirm", use_container_width=True, type="primary")
            with c2:
                if st.button("✖ Cancel", use_container_width=True):
                    st.session_state['pantry_action'] = None
                    st.rerun()

        if submitted:
            if not q_name.strip() or not q_pin.strip():
                st.error("⚠️ Please fill in all mandatory fields (Name and PIN).")
            else:
                data = {"name": q_name, "designation": q_desig, "comment": q_comment, "pin": q_pin, "urgent": q_is_urgent, "urgent_reason": q_reason}
                doc_ref.update({"queue": firestore.ArrayUnion([data])})
                alert = f"🍳 *Pantry Queue Update*\n👤 User: {q_name} joined queue for Pantry."
                if q_comment.strip(): alert += f"\n📝 *Note:* _{q_comment.strip()}_"
                if q_is_urgent: alert += f"\n🔥 *URGENT*: {q_reason}"
                send_telegram(alert, selected_hostel)
                st.session_state['pantry_action'] = None
                st.rerun()
        st.stop()

    # State: Start Queue
    if st.session_state.get('pantry_action') == 'Start Queue':
        st.markdown(f"### Start Using Pantry ({queue[0]['name']})")
        with st.container(border=True):
            sp_name = st.text_input("Name *", value=queue[0]['name'])
            sp_desig = st.selectbox("Designation *", ["PhD", "PDF", "Project Student", "Visitor"], index=["PhD", "PDF", "Project Student", "Visitor"].index(queue[0]['designation']) if queue[0]['designation'] in ["PhD", "PDF", "Project Student", "Visitor"] else 0)
            sp_comments = st.text_input("Comments (equipments used etc.)", value=queue[0].get('comment', ''))
            sp_pin = st.text_input("PIN *", type="password")
            
            c1, c2 = st.columns(2)
            with c1:
                sp_submit = st.button("Mark as In Use", use_container_width=True, type="primary")
            with c2:
                if st.button("✖ Cancel", use_container_width=True):
                    st.session_state['pantry_action'] = None
                    st.rerun()

        if sp_submit:
            if not sp_name.strip() or not sp_pin.strip():
                st.error("⚠️ Please fill in all mandatory fields (Name and PIN).")
            elif sp_name.strip().lower() != queue[0]['name'].strip().lower():
                st.error(f"Only {queue[0]['name']} can start!")
            else:
                queue.pop(0)
                user_data = {
                    "name": sp_name,
                    "designation": sp_desig,
                    "comments": sp_comments,
                    "pin": sp_pin,
                    "start_time": get_current_time().isoformat()
                }
                doc_ref.set({"current_user": user_data, "queue": queue})
                msg = f"🍳 *Pantry In Use*\n👤 {sp_name}"
                if sp_comments.strip():
                    msg += f"\n📝 Equipment: {sp_comments}"
                send_telegram(msg, selected_hostel)
                st.session_state['pantry_action'] = None
                st.rerun()
        st.stop()

    # Main Pantry View
    timeout_happened = False
    if current_user:
        st.error(f"🔴 IN USE BY: {current_user['name']} ({current_user['designation']})")
        if current_user.get('comments'):
            st.info(f"📝 Equipment Used / Comments: {current_user['comments']}")
        st.write(f"🕒 Started at: {format_time(current_user['start_time'])}")
        
        with st.expander("⚙️ Finish Cooking"):
            fin_pin = st.text_input("PIN *", type="password", key="fin_pin_pantry")
            fin_submit = st.button("Mark as Not In Use", type="primary", use_container_width=True, key="fin_submit_pantry")
            
        if fin_submit:
            if fin_pin == current_user['pin'] or fin_pin == MASTER_PIN:
                doc_ref.update({
                    "current_user": firestore.DELETE_FIELD,
                    "last_free_time": get_current_time().isoformat()
                })
                start_dt = datetime.fromisoformat(current_user['start_time'])
                duration = int((get_current_time() - start_dt).total_seconds() / 60)
                log_data = {
                    "timestamp": get_current_time().isoformat(),
                    "user": current_user['name'],
                    "designation": current_user['designation'],
                    "comments": current_user['comments'],
                    "duration_mins": duration
                }
                db.collection(f"{hostel_id}_logs").add(log_data)
                msg = f"🍳 *Pantry Free*\n✅ {current_user['name']} finished cooking."
                if queue: msg += f"\n👉 Next: *{queue[0]['name']}*"
                send_telegram(msg, selected_hostel)
                trigger_browser_notification(f"[{selected_hostel}] ✅ Pantry Free!", "Pantry is available.")
                st.rerun()
            else:
                st.error("⚠️ Incorrect PIN.")
    else:
        st.success("🟢 PANTRY IS AVAILABLE")
        effective_free_time = None
        if last_free_time_str:
            effective_free_time = datetime.fromisoformat(last_free_time_str)

        if queue and effective_free_time:
            buffer_deadline = effective_free_time + timedelta(minutes=BUFFER_MINUTES)
            mins_left = int((buffer_deadline - get_current_time()).total_seconds() / 60)
            
            if mins_left > 0:
                st.warning(f"⏳ **{queue[0]['name']}** has {mins_left} mins to claim.")
            else:
                st.error(f"⚠️ {queue[0]['name']} timed out.")
                timeout_happened = True
                
                if len(queue) == 1:
                    timed_out_user = queue.pop(0)
                    doc_ref.update({"queue": queue, "last_free_time": get_current_time().isoformat()})
                    send_telegram(f"⚠️ *Pantry Queue Alert*\n{timed_out_user['name']} timed out and was automatically removed from the queue.", selected_hostel)
                    st.rerun()
        
        if not queue or (queue and timeout_happened and len(queue) == 1):
            st.markdown("### Start Using Pantry")
            with st.form("start_pantry"):
                sp_name = st.text_input("Name *")
                sp_desig = st.selectbox("Designation *", ["PhD", "PDF", "Project Student", "Visitor"])
                sp_comments = st.text_input("Comments (equipments used etc.)", placeholder="e.g., Induction stove, Pan")
                sp_pin = st.text_input("PIN *", type="password")
                
                sp_submit = st.form_submit_button("Mark as In Use", type="primary", use_container_width=True)
                
            if sp_submit:
                if not sp_name.strip() or not sp_pin.strip():
                    st.error("⚠️ Please fill in all mandatory fields (Name and PIN).")
                else:
                    user_data = {
                        "name": sp_name,
                        "designation": sp_desig,
                        "comments": sp_comments,
                        "pin": sp_pin,
                        "start_time": get_current_time().isoformat()
                    }
                    doc_ref.set({"current_user": user_data, "queue": queue})
                    msg = f"🍳 *Pantry In Use*\n👤 {sp_name}"
                    if sp_comments.strip():
                        msg += f"\n📝 Equipment: {sp_comments}"
                    send_telegram(msg, selected_hostel)
                    st.rerun()

    # Queue Display
    if queue:
        st.divider()
        st.write(f"**Queue ({len(queue)})**")
        for idx, q_user in enumerate(queue):
            urgency_icon = "🔥" if q_user.get('urgent') else ""
            desig_str = q_user.get('designation', '')
            name_str = f"{q_user['name']} ({desig_str})" if desig_str else q_user['name']
            
            with st.expander(f"{idx+1}. {name_str} {urgency_icon}"):
                if q_user.get('urgent_reason'):
                    st.markdown(f":fire: <span class='urgent-text'>{q_user['urgent_reason']}</span>", unsafe_allow_html=True)
                if q_user.get('comment'):
                    st.info(f"📝 Note: {q_user['comment']}")
                
                action_pin = st.text_input("PIN", type="password", key=f"qpin_pantry_{idx}")
                c_swap, c_leave = st.columns(2)
                
                if idx < len(queue) - 1:
                    if c_swap.button(f"▼ Swap Down", key=f"swap_pantry_{idx}"):
                        if action_pin == q_user['pin'] or action_pin == MASTER_PIN:
                            queue[idx], queue[idx+1] = queue[idx+1], queue[idx]
                            doc_ref.update({"queue": queue})
                            st.rerun()
                
                if c_leave.button("❌ Leave", key=f"lv_pantry_{idx}"):
                    if action_pin == q_user['pin'] or action_pin == MASTER_PIN:
                        queue.pop(idx)
                        doc_ref.update({"queue": queue})
                        st.rerun()

    st.divider()
    show_join = False
    
    if current_user:
        show_join = True
    elif queue:
        show_join = True
        
        if timeout_happened and len(queue) > 1:
            st.write(f"**{queue[0]['name']} missed their turn.**")
            if st.button(f"🚀 Skip to {queue[1]['name']}", key="skip_pantry"):
                 timed_out_user = queue.pop(0)
                 doc_ref.update({"queue": queue, "last_free_time": get_current_time().isoformat()})
                 send_telegram(f"⚠️ *Pantry Queue Alert*\n{timed_out_user['name']} timed out.\n👉 Next: {queue[0]['name']} starts now.", selected_hostel)
                 st.rerun()

        if st.button(f"Start ({queue[0]['name']})", use_container_width=True, key="btn_sq_pantry"):
            st.session_state['pantry_action'] = 'Start Queue'
            st.rerun()

    if show_join:
        if st.button("Join Queue", use_container_width=True, key="btn_jq_pantry"):
            st.session_state['pantry_action'] = 'Join Queue'
            st.rerun()

    st.stop()

if selected_hostel == "Kritika Hostel":
    DB_COLLECTION = "machines_kritika"
    MACHINES = ["Kritika Washer (Floor 3)", "Kritika Washer (Floor 2)", "Kritika Dryer (Floor 1)"]
else:
    DB_COLLECTION = "machines_rohini"
    MACHINES = ["Rohini Washer (GF1)", "Rohini washer (GF2)", "Rohini Washer (UF)", "Rohini Dryer"]

if st.session_state.get('active_action'):
    action = st.session_state['active_action']
    machine_name = action['machine_name']
    act_type = action['type']
    queue_0_name = action.get('queue_0_name', '')
    
    st.markdown(f"## 🧺 {machine_name}")
    st.markdown(f"### {act_type.replace('_', ' ').title()}")
    
    doc_ref = db.collection(DB_COLLECTION).document(machine_name)
    doc_snap = doc_ref.get()
    m_data = doc_snap.to_dict() if doc_snap.exists else {}
    queue = m_data.get('queue', [])
    
    with st.container(border=True):
        if act_type == 'Join Queue':
            q_name = st.text_input("Name *")
            q_desig = st.selectbox("Designation *", ["PhD", "PDF", "Project Student", "Visitor"])
            q_comment = st.text_input("Comment (Optional)", placeholder="e.g., Handle with care")
            q_is_urgent = st.checkbox("🔥 Urgent?")
            q_reason = st.text_input("Reason") if q_is_urgent else ""
            q_pin = st.text_input("PIN *", type="password")
            
            submitted = st.button("Confirm", use_container_width=True, type="primary")
        else:
            name = st.text_input("Name *")
            desig = st.selectbox("Designation *", ["PhD", "PDF", "Project Student", "Visitor"])
            
            dur_choice = st.selectbox("Duration (mins) *", ["30", "45", "60", "90", "120", "Custom (Manual Input)"], index=1)
            if dur_choice == "Custom (Manual Input)":
                duration = st.number_input("Enter Manual Duration (mins) *", min_value=15, max_value=200, value=45, step=5)
            else:
                duration = int(dur_choice)
                
            comment = st.text_input("Comment (Optional)", placeholder="e.g., Handle with care")
            pin = st.text_input("PIN *", type="password")
            
            submitted = st.button("Start", use_container_width=True, type="primary")

    if st.button("✖ Cancel / Go Back", use_container_width=True):
        st.session_state['active_action'] = None
        st.rerun()

    if submitted:
        if act_type == 'Join Queue':
            if not q_name.strip() or not q_pin.strip():
                st.error("⚠️ Please fill in all mandatory fields (Name and PIN).")
            else:
                data = {"name": q_name, "designation": q_desig, "comment": q_comment, "pin": q_pin, "urgent": q_is_urgent, "urgent_reason": q_reason}
                doc_ref.update({"queue": firestore.ArrayUnion([data])})
                alert = f"📝 *Queue Update*\n👤 User: {q_name} joined queue for {machine_name}."
                if q_comment.strip(): alert += f"\n📝 *Note:* _{q_comment.strip()}_"
                if q_is_urgent: alert += f"\n🔥 *URGENT*: {q_reason}"
                send_telegram(alert, selected_hostel)
                st.session_state['active_action'] = None
                st.rerun()
        else:
            if not name.strip() or not pin.strip():
                st.error("⚠️ Please fill in all mandatory fields (Name and PIN).")
            elif act_type == 'Start Queue' and name.strip().lower() != queue_0_name.strip().lower():
                st.error(f"Only {queue_0_name} can start!")
            else:
                if act_type == 'Start Queue':
                    queue.pop(0)
                end_val = get_current_time() + timedelta(minutes=duration)
                user_data = {"name": name, "designation": desig, "comment": comment, "pin": pin, "start_time": get_current_time().isoformat(), "end_time": end_val.isoformat(), "timeout_alert_sent": False}
                doc_ref.set({"current_user": user_data, "queue": queue})
                add_log(DB_COLLECTION, machine_name, name, desig, duration)
                msg = f"🧺 *{machine_name} Started*\n👤 User: {name}\n⏱ Duration: {duration} mins"
                if comment.strip(): msg += f"\n📝 *Note:* _{comment.strip()}_"
                send_telegram(msg, selected_hostel)
                st.session_state['active_action'] = None
                st.rerun()
    st.stop()

# CSS Styles
st.markdown("""
<style>
div[data-testid="stExpander"] details summary p { font-size: 1.1rem; font-weight: 600; }
.urgent-text { color: #FF4B4B; font-weight: bold; }
/* Hide 'Press Enter to apply' */
div[data-testid="InputInstructions"] { display: none !important; }
/* Input animations for mobile */
.stTextInput input, .stNumberInput input {
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
}
.stTextInput input:focus, .stNumberInput input:focus {
    box-shadow: 0 0 8px rgba(255, 75, 75, 0.4) !important;
    border-color: #FF4B4B !important;
}
</style>
""", unsafe_allow_html=True)

# Display machines side-by-side on desktop, auto-stacks vertically on mobile
cols = st.columns(len(MACHINES))

for i, machine_name in enumerate(MACHINES):
    with cols[i]:
        with st.container(border=True):
            st.subheader(f"{machine_name}")
            
            # Fetch data
            doc_ref = db.collection(DB_COLLECTION).document(machine_name)
            doc = doc_ref.get()
            machine_data = doc.to_dict() if doc.exists else {}
            
            current_user = machine_data.get("current_user", None)
            queue = machine_data.get("queue", [])
            last_free_time_str = machine_data.get("last_free_time", None)
            
            # --- LOGIC & TRIGGERS ---
            
            is_running = False
            user_name = "None"
            
            if current_user:
                end_time = datetime.fromisoformat(current_user['end_time'])
                user_name = current_user['name']
                
                # CASE 1: Still Running
                if get_current_time() < end_time:
                    is_running = True
                
                # CASE 2: Time JUST ran out (Auto-Expiry)
                else:
                    is_running = False
                    # Check if we already sent the "Time's Up" alert
                    if not current_user.get('timeout_alert_sent', False):
                        # SEND ALERTS
                        msg = f"⏰ *TIME IS UP!*\n{user_name}'s cycle finished on {machine_name}."
                        if queue: msg += f"\n👉 Next: *{queue[0]['name']}*"
                        else: msg += "\n✅ Machine is now free."
                        
                        send_telegram(msg, selected_hostel)
                        trigger_browser_notification(f"[{selected_hostel}] ⏰ Time's Up!", f"{user_name} finished on {machine_name}")
                        
                        # Mark as sent
                        current_user['timeout_alert_sent'] = True
                        doc_ref.update({"current_user": current_user})
                        st.rerun()

            # Retrieve Previous State (for Browser Notifications)
            state_key = f"{selected_hostel}_{machine_name}"
            prev_state = st.session_state['machine_states'].get(state_key, {
                'is_running': is_running,
                'queue_len': len(queue),
                'first_in_line': queue[0]['name'] if queue else None
            })

            # Browser Trigger: Machine became free
            if prev_state['is_running'] and not is_running:
                trigger_browser_notification(f"[{selected_hostel}] ✅ Machine Free!", f"{machine_name} is available.")

            # Update State
            st.session_state['machine_states'][state_key] = {
                'is_running': is_running,
                'queue_len': len(queue),
                'first_in_line': queue[0]['name'] if queue else None
            }

            # --- DISPLAY UI ---
            if is_running:
                desig_str = current_user.get('designation', '')
                title_str = f"🔴 BUSY: {current_user['name']} ({desig_str})" if desig_str else f"🔴 BUSY: {current_user['name']}"
                st.error(title_str)
                
                remaining = int((end_time - get_current_time()).total_seconds() / 60)
                st.metric("Time Left", f"{remaining} min", delta_color="inverse")
                
                avail_time_str = format_time(end_time)
                st.write(f"🕒 **Expected Available at:** `{avail_time_str}`")
                
                if current_user.get('comment'):
                    st.info(f"📝 Note: {current_user['comment']}")
                
                with st.expander("⚙️ Finish early / Extend time"):
                    c_pin, c_add = st.columns([2, 1])
                    with c_pin:
                        pin_input = st.text_input("PIN *", type="password", key=f"pin_{machine_name}")
                    with c_add:
                        add_time = st.number_input("Add Mins", min_value=5, value=15, step=5, key=f"time_{machine_name}")
                    
                    st.write("") # Spacer
                    c1, c2 = st.columns(2)
                    with c1:
                        add_btn = st.button("Add Time", use_container_width=True, key=f"add_{machine_name}")
                    with c2:
                        end_btn = st.button("Finish Early", use_container_width=True, key=f"end_{machine_name}")
                        
                    if add_btn:
                        if not pin_input.strip():
                            st.error("⚠️ Please enter PIN.")
                        elif pin_input == current_user['pin'] or pin_input == MASTER_PIN:
                            new_end = end_time + timedelta(minutes=add_time)
                            current_user['end_time'] = new_end.isoformat()
                            # Reset alert flag if adding time
                            current_user['timeout_alert_sent'] = False
                            doc_ref.update({"current_user": current_user})
                            st.rerun()
                        else:
                            st.error("Wrong PIN")

                    if end_btn:
                        if not pin_input.strip():
                            st.error("⚠️ Please enter PIN.")
                        elif pin_input == current_user['pin'] or pin_input == MASTER_PIN:
                            doc_ref.update({
                                "current_user": firestore.DELETE_FIELD,
                                "last_free_time": get_current_time().isoformat()
                            })
                            # MANUAL FINISH ALERT
                            msg = f"✅ *{machine_name} FINISHED EARLY*\nUser: {current_user['name']}"
                            if queue: msg += f"\n👉 Next: *{queue[0]['name']}*"
                            send_telegram(msg, selected_hostel)
                            st.rerun()
                        else:
                            st.error("Wrong PIN")
            else:
                st.success("🟢 AVAILABLE")
                
                effective_free_time = None
                if last_free_time_str:
                    effective_free_time = datetime.fromisoformat(last_free_time_str)
                elif current_user: 
                    effective_free_time = datetime.fromisoformat(current_user['end_time'])

                timeout_happened = False
                if queue and effective_free_time:
                    buffer_deadline = effective_free_time + timedelta(minutes=BUFFER_MINUTES)
                    mins_left = int((buffer_deadline - get_current_time()).total_seconds() / 60)
                    
                    if mins_left > 0:
                        st.warning(f"⏳ **{queue[0]['name']}** has {mins_left} mins to claim.")
                    else:
                        st.error(f"⚠️ {queue[0]['name']} timed out.")
                        timeout_happened = True
                        
                        if len(queue) == 1:
                            timed_out_user = queue.pop(0)
                            doc_ref.update({"queue": queue, "last_free_time": get_current_time().isoformat()})
                            send_telegram(f"⚠️ *Queue Alert*\n{timed_out_user['name']} timed out and was automatically removed from the queue for {machine_name}.", selected_hostel)
                            st.rerun()

            # --- QUEUE DISPLAY ---
            if queue:
                st.divider()
                st.write(f"**Queue ({len(queue)})**")
                for idx, q_user in enumerate(queue):
                    urgency_icon = "🔥" if q_user.get('urgent') else ""
                    desig_str = q_user.get('designation', '')
                    name_str = f"{q_user['name']} ({desig_str})" if desig_str else q_user['name']
                    
                    with st.expander(f"{idx+1}. {name_str} {urgency_icon}"):
                        if q_user.get('urgent_reason'):
                            st.markdown(f":fire: <span class='urgent-text'>{q_user['urgent_reason']}</span>", unsafe_allow_html=True)
                        if q_user.get('comment'):
                            st.info(f"📝 Note: {q_user['comment']}")
                        
                        action_pin = st.text_input("PIN", type="password", key=f"qpin_{machine_name}_{idx}")
                        c_swap, c_leave = st.columns(2)
                        
                        if idx < len(queue) - 1:
                            if c_swap.button(f"▼ Swap Down", key=f"swap_{machine_name}_{idx}"):
                                if action_pin == q_user['pin'] or action_pin == MASTER_PIN:
                                    queue[idx], queue[idx+1] = queue[idx+1], queue[idx]
                                    doc_ref.update({"queue": queue})
                                    st.rerun()
                        
                        if c_leave.button("❌ Leave", key=f"lv_{machine_name}_{idx}"):
                            if action_pin == q_user['pin'] or action_pin == MASTER_PIN:
                                queue.pop(idx)
                                doc_ref.update({"queue": queue})
                                st.rerun()

            # --- ACTION BUTTONS ---
            st.divider()
            
            show_join = False
            
            if is_running:
                show_join = True
            elif queue:
                show_join = True
                
                if timeout_happened and len(queue) > 1:
                    st.write(f"**{queue[0]['name']} missed their turn.**")
                    if st.button(f"🚀 Skip to {queue[1]['name']}", key=f"skip_{machine_name}"):
                         timed_out_user = queue.pop(0)
                         doc_ref.update({"queue": queue, "last_free_time": get_current_time().isoformat()})
                         send_telegram(f"⚠️ *Queue Alert*\n{timed_out_user['name']} timed out.\n👉 Next: {queue[0]['name']} starts now.", selected_hostel)
                         st.rerun()

                if st.button(f"Start ({queue[0]['name']})", use_container_width=True, key=f"btn_sq_{machine_name}"):
                    st.session_state['active_action'] = {'type': 'Start Queue', 'machine_name': machine_name, 'queue_0_name': queue[0]['name']}
                    st.rerun()
            else:
                if st.button("Start Machine", use_container_width=True, key=f"btn_sf_{machine_name}"):
                    st.session_state['active_action'] = {'type': 'Start Machine', 'machine_name': machine_name}
                    st.rerun()

            if show_join:
                if st.button("Join Queue", use_container_width=True, key=f"btn_jq_{machine_name}"):
                    st.session_state['active_action'] = {'type': 'Join Queue', 'machine_name': machine_name}
                    st.rerun()

# --- CUSTOM JS ---
custom_js = """
<script>
    const doc = window.parent.document;
    
    // --- ACCORDION LOGIC ---
    const details = doc.querySelectorAll('div[data-testid="stExpander"] details');
    details.forEach((targetDetail, index) => {
        const savedIndex = sessionStorage.getItem('open_expander');
        
        // Restore state on reload
        if (savedIndex !== null) {
            const shouldBeOpen = parseInt(savedIndex) === index;
            const isOpen = targetDetail.hasAttribute('open');
            if (shouldBeOpen && !isOpen) {
                const summary = targetDetail.querySelector('summary');
                if (summary) summary.click();
            } else if (!shouldBeOpen && isOpen) {
                const summary = targetDetail.querySelector('summary');
                if (summary) summary.click();
            }
        }
        
        // Enforce accordion behavior on manual clicks
        if (!targetDetail.hasAttribute('data-accordion-bound')) {
            targetDetail.setAttribute('data-accordion-bound', 'true');
            
            const summary = targetDetail.querySelector('summary');
            if (summary) {
                summary.addEventListener('click', (e) => {
                    const isOpening = !targetDetail.hasAttribute('open');
                    
                    if (isOpening) {
                        sessionStorage.setItem('open_expander', index);
                        // Close all others via React click
                        details.forEach((d, i) => {
                            if (i !== index && d.hasAttribute('open')) {
                                const otherSummary = d.querySelector('summary');
                                if (otherSummary) otherSummary.click();
                            }
                        });
                    } else {
                        if (sessionStorage.getItem('open_expander') == index) {
                            sessionStorage.removeItem('open_expander');
                        }
                    }
                });
            }
        }
    });

    // --- COSMETIC BUTTON COLOR VALIDATION ---
    const colorObserver = new MutationObserver(() => {
        // Expander Buttons
        doc.querySelectorAll('div[data-testid="stExpander"]').forEach(exp => {
            if (!exp.hasAttribute('data-color-bound')) {
                const pinInputWrapper = Array.from(exp.querySelectorAll('div[data-testid="stTextInput"]')).find(w => {
                    const l = w.querySelector('label');
                    return l && l.innerText.includes('PIN *');
                });
                
                if (pinInputWrapper) {
                    exp.setAttribute('data-color-bound', 'true');
                    const pinInput = pinInputWrapper.querySelector('input[type="password"], input[type="text"]');
                    const actionBtns = Array.from(exp.querySelectorAll('button')).filter(b => 
                        b.innerText.includes('Add Time') || b.innerText.includes('Finish Early')
                    );
                    
                    if (pinInput && actionBtns.length > 0) {
                        const checkExpInputs = () => {
                            const isValid = pinInput.value.trim() !== '';
                            actionBtns.forEach(btn => {
                                if (isValid) {
                                    btn.style.setProperty('background-color', '#28a745', 'important');
                                    btn.style.setProperty('color', 'white', 'important');
                                    btn.style.setProperty('border-color', '#28a745', 'important');
                                } else {
                                    btn.style.removeProperty('background-color');
                                    btn.style.removeProperty('color');
                                    btn.style.removeProperty('border-color');
                                }
                            });
                        };
                        checkExpInputs();
                        pinInput.addEventListener('input', checkExpInputs);
                    }
                }
            }
        });
    });

    colorObserver.observe(doc.body, { childList: true, subtree: true });
</script>
"""
components.html(custom_js, height=0)
