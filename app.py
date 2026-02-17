import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta

# --- 1. SETUP FIREBASE ---
# This function ensures we only connect to the database once,
# even if you refresh the page.
if not firebase_admin._apps:
    cred = credentials.Certificate("key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 2. CONFIGURATION ---
# List your machines here. You can add more later!
MACHINES = ["Washing Machine 1", "Washing Machine 2", "Dryer 1"]

# --- 3. HELPER FUNCTIONS ---
def get_ist_time():
    # Returns current time adjusted for India (UTC+5:30)
    # Useful if you deploy to a server later.
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

def format_time(dt):
    return dt.strftime("%I:%M %p")

# --- 4. THE APP INTERFACE ---
st.set_page_config(page_title="Hostel Laundry Tracker", page_icon="🧺")
st.title("🧺 ARIES Hostel Laundry Tracker")

# Create tabs for better organization
tab1, tab2 = st.tabs(["Current Status", "Join Queue / Start"])

# === TAB 1: DASHBOARD (Who is using what?) ===
with tab1:
    st.header("Live Machine Status")

    # Create a refresh button to get latest data
    if st.button("🔄 Refresh Status"):
        st.rerun()

    # Fetch data from Firestore
    machines_ref = db.collection("machines")

    # Display each machine
    for machine_name in MACHINES:
        st.subheader(f"🏗️ {machine_name}")

        # Get the specific document for this machine
        doc = machines_ref.document(machine_name).get()

        if doc.exists:
            data = doc.to_dict()
            end_time = data.get("end_time")
            # Convert string back to datetime object
            end_time_dt = datetime.fromisoformat(end_time)
            current_time = get_ist_time()

            if current_time < end_time_dt:
                # MACHINE IS BUSY
                remaining_mins = int((end_time_dt - current_time).total_seconds() / 60)

                st.error(f"⚠️ IN USE by **{data.get('user_name')}** ({data.get('designation')})")
                st.write(f"📝 Note: {data.get('comment')}")
                st.metric("Time Remaining", f"{remaining_mins} mins", delta_color="inverse")
                st.caption(f"Free at approx: {format_time(end_time_dt)}")

                # POWER CUT FEATURE
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"⚡ Power Cut (+15 mins) for {machine_name}"):
                        new_end = end_time_dt + timedelta(minutes=15)
                        machines_ref.document(machine_name).update({"end_time": new_end.isoformat()})
                        st.success("Time extended!")
                        st.rerun()
                with col2:
                    if st.button(f"✅ Finish Early ({machine_name})"):
                        machines_ref.document(machine_name).delete()
                        st.rerun()

            else:
                # MACHINE IS TECHNICALLY FREE BUT DATA EXISTS (Expired Timer)
                st.success("✅ FREE TO USE")
                st.caption("Previous timer finished.")
                machines_ref.document(machine_name).delete() # Clean up
        else:
            # NO DATA = FREE
            st.success("✅ FREE TO USE")

        st.divider()

# === TAB 2: START A SESSION ===
with tab2:
    st.header("Start a Session")

    with st.form("usage_form"):
        name = st.text_input("Your Name")
        designation = st.selectbox("Designation", ["PhD Scholar", "JRF/SRF", "Staff", "Visitor"])
        selected_machine = st.selectbox("Select Machine", MACHINES)
        duration = st.slider("Duration (minutes)", 15, 120, 45)
        comment = st.text_input("Comments (e.g., 'Heavy load', 'Don't touch')")

        submitted = st.form_submit_button("Start Machine")

        if submitted:
            if name:
                # Calculate end time
                end_time = get_ist_time() + timedelta(minutes=duration)

                # Save to Firestore
                db.collection("machines").document(selected_machine).set({
                    "user_name": name,
                    "designation": designation,
                    "start_time": get_ist_time().isoformat(),
                    "end_time": end_time.isoformat(),
                    "comment": comment
                })

                st.success(f"Started {selected_machine}! It will end at {format_time(end_time)}.")
                st.balloons()
            else:
                st.error("Please enter your name.")
