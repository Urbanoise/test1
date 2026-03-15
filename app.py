import streamlit as st
import matplotlib.pyplot as plt

st.title("Tbilisi Traffic Count")
st.write("A simple traffic visualization")

hours = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
vehicles = [320, 580, 410, 390, 450, 420, 380, 490, 620, 710]

fig, ax = plt.subplots()
ax.plot(hours, vehicles, marker='o', color='steelblue')
ax.set_xlabel("Hour of Day")
ax.set_ylabel("Vehicle Count")
ax.set_title("Hourly Traffic Volume")

st.pyplot(fig)
