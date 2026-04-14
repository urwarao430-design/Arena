import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
import urllib.parse
import re
from fpdf import FPDF
from streamlit_mic_recorder import mic_recorder 
from streamlit_autorefresh import st_autorefresh

# 1. PAGE CONFIG & AUTO-REFRESH
st.set_page_config(page_title="Arena", layout="wide")
st_autorefresh(interval=60000, key="statusrefresh")

# 2. DATABASE SETUP
conn = sqlite3.connect('arena_vault.db', check_same_thread=False)
c = conn.cursor()
c.execute("PRAGMA journal_mode=WAL;") 
c.execute('''CREATE TABLE IF NOT EXISTS bookings 
             (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, phone TEXT, ground TEXT, 
              date TEXT, start_h INTEGER, duration INTEGER, status TEXT, 
              trans_id TEXT, total REAL, type TEXT DEFAULT 'Customer', p_count INTEGER DEFAULT 1)''')
c.execute('''CREATE TABLE IF NOT EXISTS blacklist (phone TEXT PRIMARY KEY)''')
conn.commit()

# --- EXECUTIVE SETTINGS ---
HEAD_PASSKEY = "rammah786"
RATES = {"Futsal Ground": 5000, "Cricket Pitch A": 3500, "Cricket Pitch B": 3500, "Badminton Court": 1500, "Pickleball Court": 3000}
HOURS = list(range(7, 24)) + list(range(0, 5))
PERSON_OPTIONS = list(range(1, 31))

# 3. RECEIPT GENERATOR
def generate_grocery_receipt(row):
    pdf = FPDF(format=(80, 150)) 
    pdf.add_page()
    pdf.set_font("Courier", 'B', 12)
    pdf.cell(0, 5, "Arena", ln=True, align='C')
    pdf.set_font("Courier", size=8)
    pdf.cell(0, 5, f"Date: {row['date']}", ln=True, align='C')
    pdf.cell(0, 5, "-"*30, ln=True, align='C')
    pdf.ln(4)
    pdf.set_font("Courier", 'B', 10)
    pdf.cell(0, 5, f"CUSTOMER: {row['name'][:15]}", ln=True)
    pdf.cell(0, 5, f"GROUND:   {row['ground']}", ln=True)
    pdf.cell(0, 5, f"TIME:     {row['start_h']}:00", ln=True)
    pdf.cell(0, 5, f"PERSONS:  {row['p_count']}", ln=True)
    pdf.ln(4)
    pdf.cell(0, 5, "-"*30, ln=True, align='C')
    pdf.set_font("Courier", 'B', 12)
    pdf.cell(0, 10, f"TOTAL: Rs. {row['total']:,}", ln=True, align='R')

    return bytes(pdf.output(dest='S'))  # ✅ FIXED
# 4. PASSKEY SECURITY
if "authenticated" not in st.session_state:
    st.title("🏟️ Arena")
    passkey = st.text_input("Master Access Key", type="password", key="passkey_input")
    if st.button("Unlock Dashboard"):
        if passkey == HEAD_PASSKEY:
            st.session_state["authenticated"] = True
            st.rerun()
    st.stop()

# 5. SIDEBAR
with st.sidebar:
    st.title("🛡️ HEAD CONTROL")
    
    if "last_success" in st.session_state:
        st.success(st.session_state["last_success"])
        del st.session_state["last_success"]

    with st.expander("⭐ Top 10 Loyal Customers"):
        loyalty_df = pd.read_sql_query("SELECT name, COUNT(id) as Visits FROM bookings GROUP BY phone ORDER BY Visits DESC LIMIT 10", conn)
        if not loyalty_df.empty: 
            st.table(loyalty_df)

    with st.expander("🚫 Blacklist Manager"):
        ban_num = st.text_input("Phone to Ban", key="ban_phone_input")
        if st.button("Confirm Ban"):
            c.execute("INSERT OR IGNORE INTO blacklist (phone) VALUES (?)", (ban_num,))
            conn.commit()
            st.warning("Number Banned.")

    st.divider()

    # NEW RESERVATION
    m_mode = st.toggle("🛠️ Maintenance Mode")
    st.header("📝 New Reservation")

    name = st.text_input("Name", value="MAINTENANCE" if m_mode else "", key="name_input")
    c_code = st.selectbox("Code", ["+92", "+971", "+966"])
    phone_raw = st.text_input("Phone", key="phone_input")
    ground = st.selectbox("Select Ground", list(RATES.keys()))
    date_val = st.date_input("Date", min_value=date.today())
    
    p_count = st.selectbox("Person Count", PERSON_OPTIONS, index=0)
    start_h = st.selectbox("Start Hour", HOURS, format_func=lambda x: f"{x:02d}:00")
    duration = st.number_input("Duration (h)", 1, 5)
    
    pay_method = st.radio("Payment", ["Cash", "Online Payment"])
    t_id = st.text_input("Transaction ID", key="txn_input") if pay_method == "Online Payment" else ""
    
    total_fee = (RATES[ground] * duration)

    if st.button("Confirm & Save"):
        full_phone = f"{c_code.replace('+', '')}{phone_raw.lstrip('0')}"
        end_h_val = start_h + duration

        c.execute("SELECT name FROM bookings WHERE ground=? AND date=? AND NOT (start_h + duration <= ? OR start_h >= ?)", 
                  (ground, str(date_val), start_h, end_h_val))
        conflict = c.fetchone()

        if conflict:
            st.error(f"❌ SLOT OCCUPIED by {conflict}")
        else:
            c.execute("INSERT INTO bookings (name, phone, ground, date, start_h, duration, status, trans_id, total, p_count) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (name, full_phone, ground, str(date_val), start_h, duration, "VERIFIED" if t_id or m_mode else "UNPAID", t_id, total_fee, p_count))
            conn.commit()

            st.session_state["last_success"] = f"✅ SUCCESSFUL: {name}"
            alert = f"Booking Confirmation\nGround: {ground}\nTime: {start_h}:00\nPlayers: {p_count}\nName: {name}"
            st.session_state["wa_link"] = f"https://web.whatsapp.com/send?text={urllib.parse.quote(alert)}"
            st.rerun()

    if "wa_link" in st.session_state:
        st.link_button("📲 Share to Group", st.session_state["wa_link"])

# MAIN DASHBOARD
st.title("🏟️ AL-RAMMAH Farm House: Live Admin")

st.subheader("Current Ground Status")
status_cols = st.columns(len(RATES))

for i, g_name in enumerate(RATES.keys()):
    c.execute("SELECT name FROM bookings WHERE ground=? AND date=? AND start_h <= ? AND (start_h+duration) > ?", 
              (g_name, str(date.today()), datetime.now().hour, datetime.now().hour))
    active = c.fetchone()

    with status_cols[i]:
        if active:
            st.error(f"🔴 {g_name}\n{active}")
        else:
            st.success(f"🟢 {g_name}\nFREE")

st.divider()

t_df = pd.read_sql_query("SELECT total, status FROM bookings WHERE date = ?", conn, params=(str(date.today()),))

m1, m2, m3 = st.columns(3)
m1.metric("Today's Slots", len(t_df))
m2.metric("Collected", f"Rs. {t_df[t_df['status']=='VERIFIED']['total'].sum():,}")
m3.metric("Pending", f"Rs. {t_df[t_df['status']!='VERIFIED']['total'].sum():,}")

st.divider()

col_s1, col_s2 = st.columns(2)

with col_s1:
    with open("arena_vault.db", "rb") as f:
        st.download_button("📁 Download System DB (.db)", f, file_name=f"Backup_{date.today()}.db")

with col_s2:
    master_df = pd.read_sql_query("SELECT * FROM bookings", conn)
    st.download_button("📊 Download Business Excel (.csv)", master_df.to_csv(index=False), file_name=f"Excel_{date.today()}.csv")

# DAILY LIST
st.subheader("📋 Daily Schedule")

view_date = st.date_input("View List:", value=date.today())
df_view = pd.read_sql_query("SELECT * FROM bookings WHERE date = ?", conn, params=(str(view_date),))

if not df_view.empty:
    for _, row in df_view.iterrows():
        c1, c2, c3, c4, c5, c6 = st.columns([2, 1, 1, 1, 0.5, 1])

        with c1:
            st.write(f"*{row['name']}* | {row['ground']}")

        with c2:
            st.write(f"🕒 {row['start_h']}:00")

        with c3:
            color = "#00FF00" if row['status'] == "VERIFIED" else "#FF4B4B"
            st.markdown(f"<span style='color:{color}; font-weight:bold;'>{row['status']}</span>", unsafe_allow_html=True)

        with c4:
            if row['status'] == "UNPAID" and st.button("Paid", key=f"pay_{row['id']}"):
                c.execute("UPDATE bookings SET status='VERIFIED' WHERE id=?", (row['id'],))
                conn.commit()
                st.rerun()

        with c5:
            if st.button("🗑️", key=f"del_{row['id']}"):
                c.execute("DELETE FROM bookings WHERE id=?", (row['id'],))
                conn.commit()
                st.rerun()

        with c6:
            slip = generate_grocery_receipt(row)
            st.download_button("🧾 Slip", slip, f"Slip_{row['id']}.pdf", "application/pdf")