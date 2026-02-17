import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import pytz

# --- 1. SETUP FIREBASE ---
# Using the dictionary method (Bulletproof)
if not firebase_admin._apps:
    key_dict = dict(st.secrets["firebase"])
    cred = credentials.Certificate(key_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 2. CONFIGURATION ---
MACHINES = ["Washing Machine 1", "Washing Machine 2", "Dryer 1"]
IST = pytz.timezone('Asia/Kolkata')

# --- 3. HELPER FUNCTIONS ---
def get_current_time():
    return datetime.now(IST)

def format_time(dt):
    # If dt is a string (from database), convert it first
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime("%I:%M %p")

# --- 4. APP INTERFACE ---
st.set_page_config(page_title="Hostel Laundry", page_icon="🧺", layout="wide")
st.title("🧺 ARIES Hostel Laundry Tracker")
st.caption("Live Status • Queue System • Power Cut Management")

# We use columns to make it compact (Side-by-Side view)
cols = st.columns(len(MACHINES))

# --- MAIN LOOP FOR MACHINES ---
for i, machine_name in enumerate(MACHINES):
    with cols[i]:
        # Create a container for each machine to make it look like a card
        with st.container(border=True):
            st.subheader(f"{machine_name}")
            
            # Fetch data
            doc_ref = db.collection("machines").document(machine_name)
            doc = doc_ref.get()
            machine_data = doc.to_dict() if doc.exists else {}
            
            # --- STATUS LOGIC ---
            current_user = machine_data.get("current_user", None)
            queue = machine_data.get("queue", [])
            
            # Check if machine is actually running
            is_running = False
            if current_user:
                end_time = datetime.fromisoformat(current_user['end_time'])
                if get_current_time() < end_time:
                    is_running = True
                else:
                    # Timer expired, but data is there. 
                    # If queue has people, move next person in? 
                    # For now, just show "Finished"
                    pass

            # --- DISPLAY STATUS ---
            if is_running:
                st.error(f"🔴 BUSY")
                st.write(f"👤 **{current_user['name']}** ({current_user['designation']})")
                
                remaining = int((end_time - get_current_time()).total_seconds() / 60)
                st.metric("Time Left", f"{remaining} min", delta_color="inverse")
                st.caption(f"Ends at: {format_time(end_time)}")
                st.info(f"📝 {current_user.get('comment', 'No comments')}")

                # --- POWER CUT & END SESSION (Protected by PIN) ---
                with st.expander("⚙️ Settings (User Only)"):
                    pin_input = st.text_input(f"Enter PIN for {machine_name}", type="password", key=f"pin_{machine_name}")
                    
                    # Manual Power Cut Time
                    add_time = st.number_input("Add Mins", min_value=5, value=15, step=5, key=f"time_{machine_name}")
                    
                    c1, c2 = st.columns(2)
                    if c1.button("Add Time", key=f"add_{machine_name}"):
                        if pin_input == current_user['pin']:
                            new_end = end_time + timedelta(minutes=add_time)
                            current_user['end_time'] = new_end.isoformat()
                            doc_ref.update({"current_user": current_user})
                            st.rerun()
                        else:
                            st.error("Wrong PIN!")

                    if c2.button("Finish", key=f"end_{machine_name}"):
                        if pin_input == current_user['pin']:
                            # If queue is empty, clear machine. If not, logic to pop queue (optional)
                            # For simplicity: Clear machine, let next person claim it.
                            doc_ref.update({"current_user": firestore.DELETE_FIELD})
                            st.rerun()
                        else:
                            st.error("Wrong PIN!")

            else:
                st.success("🟢 AVAILABLE")
                st.write("Machine is free to use.")

            # --- QUEUE DISPLAY ---
            if queue:
                st.divider()
                st.write(f"**Queue ({len(queue)})**")
                for idx, q_user in enumerate(queue):
                    st.text(f"{idx+1}. {q_user['name']} ({q_user['designation']})")

            # --- ACTION FORM (Start or Join Queue) ---
            st.divider()
            
            # Determine button text
            action_text = "Start Machine" if not is_running else "Join Queue"
            
            with st.popover(action_text):
                with st.form(f"form_{machine_name}"):
                    name = st.text_input("Name")
                    desig = st.selectbox("Designation", ["PhD", "JRF/SRF", "Staff"], key=f"des_{machine_name}")
                    if not is_running:
                        duration = st.slider("Duration (mins)", 15, 120, 45, key=f"dur_{machine_name}")
                    else:
                        duration = 0 # Not needed for queue
                        
                    comment = st.text_input("Comment", key=f"com_{machine_name}")
                    pin = st.text_input("Set 4-digit PIN (To stop later)", max_chars=4, type="password", key=f"setpin_{machine_name}")
                    
                    submitted = st.form_submit_button("Confirm")
                    
                    if submitted and name and pin:
                        user_data = {
                            "name": name,
                            "designation": desig,
                            "comment": comment,
                            "pin": pin,
                            "timestamp": get_current_time().isoformat()
                        }
                        
                        if is_running:
                            # ADD TO QUEUE
                            # We use array_union to append to the list
                            doc_ref.update({"queue": firestore.ArrayUnion([user_data])})
                            st.toast(f"Added {name} to queue!")
                        else:
                            # START MACHINE
                            end_time_val = get_current_time() + timedelta(minutes=duration)
                            user_data["start_time"] = get_current_time().isoformat()
                            user_data["end_time"] = end_time_val.isoformat()
                            
                            # If there was a queue, theoretically we should check if this user is first.
                            # But for simplicity, we allow 'First to Click' if machine is Free.
                            doc_ref.set({"current_user": user_data, "queue": queue}) # Keep queue intact
                            st.toast(f"Machine started by {name}!")
                        
                        st.rerun()
