import streamlit as st
import streamlit.components.v1 as components
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import pytz
from streamlit_autorefresh import st_autorefresh

# --- 1. SETUP FIREBASE ---
if not firebase_admin._apps:
    key_dict = dict(st.secrets["firebase"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 2. CONFIGURATION ---
# Refresh every 30 seconds to check for status changes
st_autorefresh(interval=30000, key="data_refresh")

MACHINES = ["Washing Machine (Floor 3)", "Washing Machine (Floor 2)", "Dryer (Floor 3)"]
IST = pytz.timezone('Asia/Kolkata')
MASTER_PIN = st.secrets["general"]["master_pin"]
BUFFER_MINUTES = 15

# --- 3. BROWSER NOTIFICATION SYSTEM ---
def trigger_notification(title, body):
    # This Javascript checks if the browser allows notifications and sends one
    js_code = f"""
    <script>
        function sendNotification() {{
            var title = "{title}";
            var options = {{
                body: "{body}",
                icon: "https://cdn-icons-png.flaticon.com/512/2954/2954888.png",
                requireInteraction: true // Keeps notification on screen until clicked
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
            🔔 Enable Notifications (Click Me First)
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

# Initialize Session State for Change Detection
if 'machine_states' not in st.session_state:
    st.session_state['machine_states'] = {}

# --- 5. APP INTERFACE ---
st.set_page_config(page_title="Hostel Laundry", page_icon="🧺", layout="wide")
st.title("🧺 ARIES Laundry Tracker")
st.caption("Auto-Refresh Enabled (30s) • Keep tab open for alerts")

# Sidebar for Permissions
with st.sidebar:
    st.write("### ⚙️ Settings")
    request_permission_button()
    st.info("ℹ️ You must click the button above and 'Allow' to receive alerts.")

# CSS Styles
st.markdown("""
<style>
div[data-testid="stExpander"] details summary p { font-size: 1.1rem; font-weight: 600; }
.urgent-text { color: #FF4B4B; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

cols = st.columns(len(MACHINES))

for i, machine_name in enumerate(MACHINES):
    with cols[i]:
        with st.container(border=True):
            st.subheader(f"{machine_name}")
            
            # Fetch data
            doc_ref = db.collection("machines").document(machine_name)
            doc = doc_ref.get()
            machine_data = doc.to_dict() if doc.exists else {}
            
            current_user = machine_data.get("current_user", None)
            queue = machine_data.get("queue", [])
            last_free_time_str = machine_data.get("last_free_time", None)
            
            # --- LOGIC & NOTIFICATION TRIGGERS ---
            
            # 1. Calculate Current State
            is_running = False
            user_name = "None"
            
            if current_user:
                end_time = datetime.fromisoformat(current_user['end_time'])
                user_name = current_user['name']
                if get_current_time() < end_time:
                    is_running = True
            
            # 2. Retrieve Previous State (from 30s ago)
            prev_state = st.session_state['machine_states'].get(machine_name, {
                'is_running': is_running,
                'queue_len': len(queue),
                'urgent_count': sum(1 for q in queue if q.get('urgent')),
                'first_in_line': queue[0]['name'] if queue else None
            })
            
            # --- TRIGGER 1: TIME ENDS ---
            # Machine WAS running, NOW is stopped
            if prev_state['is_running'] and not is_running:
                trigger_notification("⏰ Time's Up!", f"{user_name} finished on {machine_name}. Machine Free!")
            
            # --- TRIGGER 2: MACHINE AVAILABLE FOR QUEUE ---
            # Machine WAS running, NOW stopped, AND Queue exists
            if prev_state['is_running'] and not is_running and queue:
                next_person = queue[0]['name']
                trigger_notification("✅ Your Turn!", f"{next_person}, {machine_name} is ready for you!")

            # --- TRIGGER 3: BUFFER TIMEOUT (Next Person Notified) ---
            # If the first person in line CHANGED, but nobody started the machine... 
            # it means the previous #1 was removed/swapped/timed out.
            curr_first = queue[0]['name'] if queue else None
            if not is_running and prev_state['first_in_line'] and curr_first:
                if prev_state['first_in_line'] != curr_first:
                    trigger_notification("⚠️ Timeout / Swap", f"{prev_state['first_in_line']} removed. {curr_first} is now next!")

            # --- TRIGGER 4: EMERGENCY ADDED ---
            # Count of urgent users increased
            curr_urgent = sum(1 for q in queue if q.get('urgent'))
            if curr_urgent > prev_state['urgent_count']:
                trigger_notification("🔥 Emergency Request", f"Someone in queue for {machine_name} has an urgent need!")

            # UPDATE STATE FOR NEXT REFRESH
            st.session_state['machine_states'][machine_name] = {
                'is_running': is_running,
                'queue_len': len(queue),
                'urgent_count': curr_urgent,
                'first_in_line': curr_first
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
                
                with st.expander("⚙️ Manage / Power Cut"):
                    pin_input = st.text_input("PIN", type="password", key=f"pin_{machine_name}")
                    
                    add_time = st.number_input("Add Mins (Power Cut)", min_value=5, value=15, step=5, key=f"time_{machine_name}")
                    
                    c1, c2 = st.columns(2)
                    if c1.button("Add Time", key=f"add_{machine_name}"):
                        if pin_input == current_user['pin'] or pin_input == MASTER_PIN:
                            new_end = end_time + timedelta(minutes=add_time)
                            current_user['end_time'] = new_end.isoformat()
                            doc_ref.update({"current_user": current_user})
                            st.rerun()
                        else:
                            st.error("Wrong PIN")

                    if c2.button("Finish Early", key=f"end_{machine_name}"):
                        if pin_input == current_user['pin'] or pin_input == MASTER_PIN:
                            doc_ref.update({
                                "current_user": firestore.DELETE_FIELD,
                                "last_free_time": get_current_time().isoformat()
                            })
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
                         queue.pop(0)
                         doc_ref.update({"queue": queue, "last_free_time": get_current_time().isoformat()})
                         st.rerun()

                with st.popover(f"Start ({queue[0]['name']})", use_container_width=True):
                    with st.form(f"st_form_{machine_name}"):
                        name = st.text_input("Name")
                        desig = st.selectbox("Designation", ["PhD", "JRF/SRF", "Staff"], key=f"d1_{machine_name}")
                        duration = st.slider("Duration", 15, 120, 45, key=f"dur1_{machine_name}")
                        comment = st.text_input("Comment (Optional)", key=f"c1_{machine_name}")
                        pin = st.text_input("PIN", type="password", key=f"p1_{machine_name}")
                        if st.form_submit_button("Start"):
                            if name.strip().lower() != queue[0]['name'].strip().lower():
                                st.error(f"Only {queue[0]['name']} can start!")
                            else:
                                queue.pop(0)
                                end_val = get_current_time() + timedelta(minutes=duration)
                                user_data = {"name": name, "designation": desig, "comment": comment, "pin": pin, "start_time": get_current_time().isoformat(), "end_time": end_val.isoformat()}
                                doc_ref.set({"current_user": user_data, "queue": queue})
                                st.rerun()
            else:
                with st.popover("Start Machine", use_container_width=True):
                    with st.form(f"free_st_{machine_name}"):
                        name = st.text_input("Name")
                        desig = st.selectbox("Designation", ["PhD", "JRF/SRF", "Staff"], key=f"d2_{machine_name}")
                        duration = st.slider("Duration", 15, 120, 45, key=f"dur2_{machine_name}")
                        comment = st.text_input("Comment (Optional)", key=f"c2_{machine_name}")
                        pin = st.text_input("PIN", type="password", key=f"p2_{machine_name}")
                        if st.form_submit_button("Start"):
                            end_val = get_current_time() + timedelta(minutes=duration)
                            user_data = {"name": name, "designation": desig, "comment": comment, "pin": pin, "start_time": get_current_time().isoformat(), "end_time": end_val.isoformat()}
                            doc_ref.set({"current_user": user_data, "queue": queue})
                            st.rerun()

            if show_join:
                with st.popover("Join Queue", use_container_width=True):
                    q_name = st.text_input("Name", key=f"qn_{machine_name}")
                    q_desig = st.selectbox("Designation", ["PhD", "JRF/SRF", "Staff"], key=f"qd_{machine_name}")
                    q_comment = st.text_input("Comment (Optional)", key=f"qc_{machine_name}")
                    q_is_urgent = st.checkbox("🔥 Urgent?", key=f"qu_{machine_name}")
                    q_reason = st.text_input("Reason", key=f"qr_{machine_name}") if q_is_urgent else ""
                    q_pin = st.text_input("PIN", type="password", key=f"qp_{machine_name}")
                    
                    if st.button("Confirm", key=f"qb_{machine_name}"):
                        if q_name and q_pin:
                            data = {"name": q_name, "designation": q_desig, "comment": q_comment, "pin": q_pin, "urgent": q_is_urgent, "urgent_reason": q_reason}
                            doc_ref.update({"queue": firestore.ArrayUnion([data])})
                            st.rerun()
