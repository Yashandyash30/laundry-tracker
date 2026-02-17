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
st.caption("Queue Priority • Urgency System • Hierarchical Swapping")

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
                
                # SETTINGS (Power Cut / Stop)
                with st.expander("⚙️ Manage Session"):
                    pin_input = st.text_input("Enter PIN or Master Key", type="password", key=f"pin_{machine_name}")
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
                    st.info(f"Reserved for: **{queue[0]['name']}**")
                else:
                    st.write("Free for everyone.")

            # --- QUEUE DISPLAY & HIERARCHICAL SWAPPING ---
            if queue:
                st.divider()
                st.write(f"**Queue ({len(queue)})**")
                
                # Expandable Control Panel for Swapping
                with st.expander("🔄 Swap / Remove User"):
                    manage_pin = st.text_input("Enter YOUR PIN to Swap/Leave", type="password", key=f"qpin_{machine_name}")
                    
                    for idx, q_user in enumerate(queue):
                        # Display User Info
                        urgency_icon = "🔥" if q_user.get('urgent') else ""
                        row_text = f"**{idx+1}. {urgency_icon} {q_user['name']}**"
                        if q_user.get('urgent_reason'):
                            row_text += f" - *\"{q_user['urgent_reason']}\"*"
                        st.markdown(row_text)

                        # ACTION BUTTONS FOR EACH USER
                        c_swap, c_remove = st.columns([2, 1])
                        
                        # Swap Button (Only if not the last person)
                        if idx < len(queue) - 1:
                            next_user = queue[idx+1]
                            if c_swap.button(f"▼ Let {next_user['name']} Pass", key=f"swap_{machine_name}_{idx}"):
                                # Verify PIN of the CURRENT user (idx) trying to be nice
                                if manage_pin == q_user['pin'] or manage_pin == MASTER_PIN:
                                    queue[idx], queue[idx+1] = queue[idx+1], queue[idx]
                                    doc_ref.update({"queue": queue})
                                    st.rerun()
                                else:
                                    st.error("Wrong PIN! You can only swap yourself down.")
                        
                        # Remove Button (Self or Admin)
                        if c_remove.button("❌", key=f"rem_{machine_name}_{idx}", help="Remove from queue"):
                             if manage_pin == q_user['pin'] or manage_pin == MASTER_PIN:
                                 queue.pop(idx)
                                 doc_ref.update({"queue": queue})
                                 st.rerun()
                             else:
                                 st.error("Wrong PIN")
                        st.divider()

            # --- START / JOIN FORM ---
            st.divider()
            
            # Logic: If queue exists, only #1 can start.
            if is_running:
                btn_text = "Join Queue"
                can_start = False
            elif queue:
                btn_text = f"Start (Only {queue[0]['name']})"
                can_start = True
            else:
                btn_text = "Start Machine"
                can_start = True

            with st.popover(btn_text):
                with st.form(f"form_{machine_name}"):
                    name = st.text_input("Name")
                    desig = st.selectbox("Designation", ["JRF/SRF", "PhD", "Staff"], key=f"d_{machine_name}")
                    
                    if can_start:
                        duration = st.slider("Duration", 15, 120, 45, key=f"t_{machine_name}")
                        is_urgent = False
                        urgent_reason = ""
                    else:
                        duration = 0
                        is_urgent = st.checkbox("🔥 I have an Urgent need!")
                        urgent_reason = st.text_input("Reason for Urgency", placeholder="e.g. Flight in 2 hours") if is_urgent else ""
                        
                    pin = st.text_input("Set 4-digit PIN", max_chars=4, type="password", key=f"p_{machine_name}")
                    submitted = st.form_submit_button("Confirm")

                    if submitted and name and pin:
                        # VALIDATION: Check if it's #1's turn
                        if can_start and queue:
                            # Simple Name Check (Case Insensitive)
                            if name.strip().lower() != queue[0]['name'].strip().lower():
                                st.error(f"❌ Rejected! It is {queue[0]['name']}'s turn.")
                                st.stop()
                            else:
                                queue.pop(0) # Valid user, remove from queue head

                        user_data = {
                            "name": name,
                            "designation": desig,
                            "pin": pin,
                            "urgent": is_urgent,
                            "urgent_reason": urgent_reason,
                            "timestamp": get_current_time().isoformat()
                        }

                        if is_running:
                            doc_ref.update({"queue": firestore.ArrayUnion([user_data])})
                            st.toast("Added to Queue!")
                        else:
                            end_time_val = get_current_time() + timedelta(minutes=duration)
                            user_data["start_time"] = get_current_time().isoformat()
                            user_data["end_time"] = end_time_val.isoformat()
                            
                            doc_ref.set({"current_user": user_data, "queue": queue})
                            st.toast("Machine Started!")
                        
                        st.rerun()
