import streamlit as st
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

# --- 3. HELPER FUNCTIONS ---
def get_current_time():
    return datetime.now(IST)

def format_time(dt):
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime("%I:%M %p")

# --- 4. APP INTERFACE ---
st.set_page_config(page_title="Hostel Laundry", page_icon="🧺", layout="wide")
st.title("🧺 ARIES Hostel Laundry Tracker")
st.caption("Live Status • Priority Queue • Emergency Handling")

# Custom CSS for cleaner list items
st.markdown("""
<style>
div[data-testid="stExpander"] details summary p {
    font-size: 1.1rem;
    font-weight: 600;
}
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
            
            # --- CHECK STATUS ---
            is_running = False
            if current_user:
                end_time = datetime.fromisoformat(current_user['end_time'])
                if get_current_time() < end_time:
                    is_running = True
            
            # --- DISPLAY BUSY STATE ---
            if is_running:
                st.error(f"🔴 BUSY: {current_user['name']}")
                remaining = int((end_time - get_current_time()).total_seconds() / 60)
                st.metric("Time Left", f"{remaining} min", delta_color="inverse")
                st.caption(f"Ends: {format_time(end_time)}")
                if current_user.get('comment'):
                    st.info(f"📝 {current_user['comment']}")
                
                # SETTINGS (Power Cut / Stop)
                with st.expander("⚙️ Admin / User Settings"):
                    pin_input = st.text_input("PIN", type="password", key=f"pin_{machine_name}")
                    add_time = st.number_input("Add Mins", 5, 60, 15, step=5, key=f"time_{machine_name}")
                    
                    c1, c2 = st.columns(2)
                    if c1.button("Add Time", key=f"add_{machine_name}"):
                        if pin_input == current_user['pin'] or pin_input == MASTER_PIN:
                            new_end = end_time + timedelta(minutes=add_time)
                            current_user['end_time'] = new_end.isoformat()
                            doc_ref.update({"current_user": current_user})
                            st.rerun()
                        else:
                            st.error("Wrong PIN")

                    if c2.button("Finish", key=f"end_{machine_name}"):
                        if pin_input == current_user['pin'] or pin_input == MASTER_PIN:
                            doc_ref.update({"current_user": firestore.DELETE_FIELD})
                            st.rerun()
                        else:
                            st.error("Wrong PIN")
            else:
                st.success("🟢 AVAILABLE")
                if queue:
                    st.warning(f"Reserved for: **{queue[0]['name']}**")
                else:
                    st.write("Free to use.")

            # --- QUEUE DISPLAY (CLICKABLE LIST) ---
            if queue:
                st.divider()
                st.write(f"**Queue ({len(queue)}) - Click name to manage**")
                
                for idx, q_user in enumerate(queue):
                    # Build Label
                    urgency_icon = "🔥" if q_user.get('urgent') else ""
                    label = f"{idx+1}. {q_user['name']} {urgency_icon}"
                    
                    with st.expander(label):
                        st.write(f"**Role:** {q_user['designation']}")
                        
                        # Show Urgency Reason in RED if it exists
                        if q_user.get('urgent_reason'):
                            st.markdown(f":fire: <span class='urgent-text'>Reason: {q_user['urgent_reason']}</span>", unsafe_allow_html=True)
                        
                        if q_user.get('comment'):
                            st.info(f"📝 Note: {q_user['comment']}")
                            
                        # CONTROLS
                        st.caption("Enter YOUR PIN to Swap or Leave:")
                        action_pin = st.text_input("PIN", type="password", key=f"qpin_{machine_name}_{idx}")
                        
                        col_swap, col_leave = st.columns(2)
                        
                        # SWAP LOGIC: Available for everyone EXCEPT the last person
                        # 1 swaps with 2, 2 swaps with 3...
                        if idx < len(queue) - 1:
                            next_person_name = queue[idx+1]['name']
                            if col_swap.button(f"▼ Swap with {next_person_name}", key=f"swap_{machine_name}_{idx}"):
                                if action_pin == q_user['pin'] or action_pin == MASTER_PIN:
                                    # Perform Swap
                                    queue[idx], queue[idx+1] = queue[idx+1], queue[idx]
                                    doc_ref.update({"queue": queue})
                                    st.rerun()
                                else:
                                    st.error("Wrong PIN")
                        else:
                            col_swap.button("▼ Swap", disabled=True, key=f"swap_dis_{machine_name}_{idx}", help="You are last in line.")

                        if col_leave.button("❌ Leave Queue", key=f"leave_{machine_name}_{idx}"):
                            if action_pin == q_user['pin'] or action_pin == MASTER_PIN:
                                queue.pop(idx)
                                doc_ref.update({"queue": queue})
                                st.rerun()
                            else:
                                st.error("Wrong PIN")

            # --- ACTION BUTTONS (START / JOIN) ---
            st.divider()
            
            show_start = False
            show_join = False
            start_label = "Start Machine"
            
            if is_running:
                show_join = True
            elif queue:
                show_start = True
                show_join = True
                start_label = f"Start ({queue[0]['name']} Only)"
            else:
                show_start = True
                start_label = "Start Machine"

            # Create columns if we need both buttons
            if show_start and show_join:
                b_col1, b_col2 = st.columns(2)
            else:
                b_col1, b_col2 = st.container(), st.container()

            # --- BUTTON 1: START MACHINE ---
            if show_start:
                with b_col1:
                    with st.popover(start_label, use_container_width=True):
                        with st.form(f"start_form_{machine_name}"):
                            st.write("### Start Machine")
                            name = st.text_input("Name")
                            desig = st.selectbox("Designation", ["JRF/SRF", "PhD", "Staff"], key=f"sd_{machine_name}")
                            duration = st.slider("Duration (mins)", 15, 120, 45, key=f"st_{machine_name}")
                            comment = st.text_input("Comment (Optional)", placeholder="e.g. Bed sheets", key=f"sc_{machine_name}")
                            pin = st.text_input("Set PIN", max_chars=4, type="password", key=f"sp_{machine_name}")
                            
                            if st.form_submit_button("Start Now"):
                                # Verification if queue exists
                                if queue:
                                    if name.strip().lower() != queue[0]['name'].strip().lower():
                                        st.error(f"❌ Only {queue[0]['name']} can start!")
                                        st.stop()
                                    else:
                                        queue.pop(0) # Remove from queue

                                end_time_val = get_current_time() + timedelta(minutes=duration)
                                user_data = {
                                    "name": name, "designation": desig, "pin": pin, 
                                    "comment": comment, "start_time": get_current_time().isoformat(),
                                    "end_time": end_time_val.isoformat()
                                }
                                doc_ref.set({"current_user": user_data, "queue": queue})
                                st.rerun()

            # --- BUTTON 2: JOIN QUEUE (DYNAMIC) ---
            if show_join:
                with b_col2:
                    with st.popover("Join Queue", use_container_width=True):
                        # NOTE: We are NOT using st.form here so we can have dynamic interactions
                        st.write("### Join Queue")
                        q_name = st.text_input("Name", key=f"qn_{machine_name}")
                        q_desig = st.selectbox("Designation", ["JRF/SRF", "PhD", "Staff"], key=f"qd_{machine_name}")
                        q_comment = st.text_input("Comment", placeholder="e.g. White clothes", key=f"qc_{machine_name}")
                        
                        # DYNAMIC URGENCY BOX
                        q_is_urgent = st.checkbox("🔥 Urgent Priority?", key=f"qu_{machine_name}")
                        q_urgent_reason = ""
                        
                        if q_is_urgent:
                            st.markdown(":fire: **Please state your emergency:**")
                            q_urgent_reason = st.text_input("Reason", placeholder="Flight in 3 hours...", key=f"qr_{machine_name}")

                        q_pin = st.text_input("Set PIN", max_chars=4, type="password", key=f"qp_{machine_name}")
                        
                        if st.button("Confirm Join", key=f"qbtn_{machine_name}"):
                            if q_name and q_pin:
                                if q_is_urgent and not q_urgent_reason:
                                    st.error("Please enter a reason for urgency.")
                                else:
                                    user_data = {
                                        "name": q_name, "designation": q_desig, "pin": q_pin,
                                        "comment": q_comment, "urgent": q_is_urgent,
                                        "urgent_reason": q_urgent_reason,
                                        "timestamp": get_current_time().isoformat()
                                    }
                                    doc_ref.update({"queue": firestore.ArrayUnion([user_data])})
                                    st.rerun()
                            else:
                                st.error("Name and PIN are required.")
