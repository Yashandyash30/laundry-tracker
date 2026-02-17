import streamlit as st
import streamlit.components.v1 as components
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import pytz

# --- 1. SETUP FIREBASE ---
if not firebase_admin._apps:
    key_dict = dict(st.secrets["firebase"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 2. CONFIGURATION ---
MACHINES = ["Washing Machine (Floor 3)", "Washing Machine (Floor 2)", "Dryer (Floor 3)"]
IST = pytz.timezone('Asia/Kolkata')
MASTER_PIN = st.secrets["general"]["master_pin"]
BUFFER_MINUTES = 15

# --- 3. JAVASCRIPT NOTIFICATION ENGINE ---
# This function injects a script that the browser runs
def trigger_notification(title, body):
    js_code = f"""
    <script>
        function sendNotification() {{
            var title = "{title}";
            var options = {{
                body: "{body}",
                icon: "https://cdn-icons-png.flaticon.com/512/2954/2954888.png"
            }};
            if (Notification.permission === "granted") {{
                new Notification(title, options);
            }} else if (Notification.permission !== "denied") {{
                Notification.requestPermission().then(function (permission) {{
                    if (permission === "granted") {{
                        new Notification(title, options);
                    }}
                }});
            }}
        }}
        sendNotification();
    </script>
    """
    components.html(js_code, height=0, width=0)

def request_permission_button():
    # Only works if the user clicks it manually
    components.html("""
    <script>
        function askPermission() {
            Notification.requestPermission().then(function(result) {
                console.log(result);
            });
        }
    </script>
    <button onclick="askPermission()" style="
        background-color: #4CAF50; color: white; padding: 10px 20px; 
        border: none; border-radius: 5px; cursor: pointer; font-size: 14px;">
        🔔 Click to Enable Alerts
    </button>
    """, height=50)

# --- 4. HELPER FUNCTIONS ---
def get_current_time():
    return datetime.now(IST)

def format_time(dt):
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime("%I:%M %p")

# --- 5. APP INTERFACE ---
st.set_page_config(page_title="Hostel Laundry", page_icon="🧺", layout="wide")
st.title("🧺 ARIES Laundry Tracker")

# Sidebar for Notification Setup
with st.sidebar:
    st.header("🔔 Notifications")
    st.write("Click below to allow browser alerts when machines become free.")
    request_permission_button()
    st.divider()
    st.info("Keep this tab open in the background to receive alerts.")

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
            
            # --- CHECK RUNNING STATUS ---
            is_running = False
            just_finished = False # Logic to detect transition
            
            if current_user:
                end_time = datetime.fromisoformat(current_user['end_time'])
                if get_current_time() < end_time:
                    is_running = True
                else:
                    # It expired naturally just now!
                    is_running = False
                    just_finished = True 

            # --- DISPLAY STATUS ---
            if is_running:
                st.error(f"🔴 BUSY: {current_user['name']}")
                remaining = int((end_time - get_current_time()).total_seconds() / 60)
                st.metric("Time Left", f"{remaining} min", delta_color="inverse")
                st.caption(f"Ends: {format_time(end_time)}")
                
                # SETTINGS
                with st.expander("⚙️ Manage"):
                    pin_input = st.text_input("PIN", type="password", key=f"pin_{machine_name}")
                    c1, c2 = st.columns(2)
                    if c1.button("Add 15m", key=f"add_{machine_name}"):
                        if pin_input == current_user['pin'] or pin_input == MASTER_PIN:
                            new_end = end_time + timedelta(minutes=15)
                            current_user['end_time'] = new_end.isoformat()
                            doc_ref.update({"current_user": current_user})
                            st.rerun()
                        else:
                            st.error("Wrong PIN")
                    if c2.button("Finish", key=f"end_{machine_name}"):
                        if pin_input == current_user['pin'] or pin_input == MASTER_PIN:
                            doc_ref.update({
                                "current_user": firestore.DELETE_FIELD,
                                "last_free_time": get_current_time().isoformat()
                            })
                            # NOTIFICATION TRIGGER (MANUAL FINISH)
                            if queue:
                                next_person = queue[0]['name']
                                trigger_notification(f"{machine_name} Free!", f"Next up: {next_person}")
                            else:
                                trigger_notification(f"{machine_name} Free!", "Machine is now available.")
                            st.rerun()
                        else:
                            st.error("Wrong PIN")
            else:
                st.success("🟢 AVAILABLE")
                
                # NOTIFICATION TRIGGER (AUTO TIMEOUT)
                # If we detected it just finished naturally in this refresh cycle
                if just_finished:
                    # We need to ensure we don't spam. 
                    # Realistically, this fires once when someone refreshes the page and sees it expired.
                    if queue:
                         trigger_notification(f"{machine_name} Finished!", f"Next: {queue[0]['name']}")
                    else:
                         trigger_notification(f"{machine_name} Finished!", "Available now.")

                # --- BUFFER LOGIC ---
                effective_free_time = None
                if last_free_time_str:
                    effective_free_time = datetime.fromisoformat(last_free_time_str)
                elif current_user and just_finished:
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
                    with st.expander(f"{idx+1}. {q_user['name']} {urgency_icon}"):
                        if q_user.get('urgent_reason'):
                            st.markdown(f":fire: <span class='urgent-text'>{q_user['urgent_reason']}</span>", unsafe_allow_html=True)
                        st.caption("Enter YOUR PIN to Swap/Leave:")
                        action_pin = st.text_input("PIN", type="password", key=f"qpin_{machine_name}_{idx}")
                        
                        c_swap, c_leave = st.columns(2)
                        
                        if idx < len(queue) - 1:
                            next_name = queue[idx+1]['name']
                            if c_swap.button(f"▼ Swap with {next_name}", key=f"swap_{machine_name}_{idx}"):
                                if action_pin == q_user['pin'] or action_pin == MASTER_PIN:
                                    queue[idx], queue[idx+1] = queue[idx+1], queue[idx]
                                    doc_ref.update({"queue": queue})
                                    st.rerun()
                                else:
                                    st.error("Wrong PIN")
                        
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
                    if st.button(f"🚀 Skip & Start ({queue[1]['name']})", key=f"skip_{machine_name}"):
                         queue.pop(0)
                         doc_ref.update({"queue": queue, "last_free_time": get_current_time().isoformat()})
                         st.rerun()

                with st.popover(f"Start ({queue[0]['name']})", use_container_width=True):
                    with st.form(f"st_form_{machine_name}"):
                        name = st.text_input("Name (Must match queue)")
                        desig = st.selectbox("Designation", ["PhD", "JRF/SRF", "Staff"])
                        duration = st.slider("Duration", 15, 120, 45)
                        pin = st.text_input("Set PIN", type="password")
                        if st.form_submit_button("Start"):
                            if name.strip().lower() != queue[0]['name'].strip().lower():
                                st.error(f"Only {queue[0]['name']} can start!")
                            else:
                                queue.pop(0)
                                end_val = get_current_time() + timedelta(minutes=duration)
                                user_data = {
                                    "name": name, "designation": desig, "pin": pin,
                                    "start_time": get_current_time().isoformat(),
                                    "end_time": end_val.isoformat()
                                }
                                doc_ref.set({"current_user": user_data, "queue": queue})
                                st.rerun()
            else:
                with st.popover("Start Machine", use_container_width=True):
                    with st.form(f"free_st_{machine_name}"):
                        name = st.text_input("Name")
                        desig = st.selectbox("Designation", ["PhD", "JRF/SRF", "Staff"])
                        duration = st.slider("Duration", 15, 120, 45)
                        pin = st.text_input("Set PIN", type="password")
                        if st.form_submit_button("Start"):
                            end_val = get_current_time() + timedelta(minutes=duration)
                            user_data = {
                                "name": name, "designation": desig, "pin": pin,
                                "start_time": get_current_time().isoformat(),
                                "end_time": end_val.isoformat()
                            }
                            doc_ref.set({"current_user": user_data, "queue": queue})
                            st.rerun()

            if show_join:
                with st.popover("Join Queue", use_container_width=True):
                    q_name = st.text_input("Name", key=f"qn_{machine_name}")
                    q_desig = st.selectbox("Designation", ["PhD", "JRF/SRF", "Staff"], key=f"qd_{machine_name}")
                    q_is_urgent = st.checkbox("🔥 Urgent?", key=f"qu_{machine_name}")
                    q_reason = st.text_input("Reason", key=f"qr_{machine_name}") if q_is_urgent else ""
                    q_pin = st.text_input("Set PIN", type="password", key=f"qp_{machine_name}")
                    
                    if st.button("Confirm Join", key=f"qb_{machine_name}"):
                        if q_name and q_pin:
                            data = {
                                "name": q_name, "designation": q_desig, "pin": q_pin,
                                "urgent": q_is_urgent, "urgent_reason": q_reason
                            }
                            doc_ref.update({"queue": firestore.ArrayUnion([data])})
                            st.rerun()
