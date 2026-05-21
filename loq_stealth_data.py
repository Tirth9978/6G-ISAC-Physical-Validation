import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt

# --- CONFIGURATION ---
MIC_ID = 1      # Your LOQ Microphone Array
SPEAKER_ID = 5  # Your LOQ Realtek Speakers
MAGIC_PHASE = 7.2 # The null point you discovered

sd.default.device = (MIC_ID, SPEAKER_ID)
fs = 44100
f_carrier = 10000.0 # 10kHz data carrier
T_msg = 1.0         # 1 second message

print(f"--- LOQ STEALTH DATA TEST (Target Null: {MAGIC_PHASE}°) ---")

# 1. Generate the "Hi" Data Payload
t = np.linspace(0, T_msg, int(fs * T_msg), endpoint=False)
MESSAGE = "Hi"
binary_msg = ''.join(format(ord(i), '08b') for i in MESSAGE)

data_signal = np.zeros_like(t)
samples_per_bit = len(data_signal) // len(binary_msg)
for i, bit in enumerate(binary_msg):
    start = i * samples_per_bit
    end = start + samples_per_bit
    if bit == '1':
        data_signal[start:end] = np.sin(2 * np.pi * f_carrier * t[start:end])
    else:
        data_signal[start:end] = -np.sin(2 * np.pi * f_carrier * t[start:end])

# --- 2. CREATE THE TWO TEST CASES ---

# Case A: Normal Stereo (Constructive)
# Both speakers play the same wave
normal_tx = np.column_stack((data_signal, data_signal))

# Case B: Stealth Stereo (Destructive)
# Right speaker is shifted by your Magic Number
phase_rad = np.radians(MAGIC_PHASE)
stealth_right = np.sin((2 * np.pi * f_carrier * t) + phase_rad)
# Multiply by the original data signal to keep the "Hi" encoding but shifted
stealth_right = np.where(data_signal > 0, stealth_right, -stealth_right)

stealth_tx = np.column_stack((data_signal, stealth_right))

# Combine with a gap in between
full_tx = np.vstack((
    normal_tx, 
    np.zeros((int(fs * 0.5), 2)), # 0.5s silence
    stealth_tx
))

print("Transmitting: [NORMAL] ... [SILENCE] ... [STEALTH]")
rx_signal = sd.playrec(full_tx, samplerate=fs, channels=1, blocking=True).flatten()

# --- 3. VISUALIZE THE DROP ---
plt.figure(figsize=(12, 5))
plt.plot(rx_signal, color='darkorange', alpha=0.7)
plt.axvline(x=fs*1.0, color='black', linestyle='--')
plt.axvline(x=fs*1.5, color='black', linestyle='--')

plt.text(fs*0.5, np.max(rx_signal), "NORMAL DATA", ha='center', weight='bold')
plt.text(fs*2.0, np.max(rx_signal), "STEALTH DATA", ha='center', weight='bold')

plt.title(f"Physical Self-Interference Cancellation on Lenovo LOQ\n(Phase Shift Applied: {MAGIC_PHASE}°)")
plt.xlabel("Samples")
plt.ylabel("Microphone Amplitude")
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# Calculate the suppression ratio
normal_rms = np.sqrt(np.mean(rx_signal[:fs]**2))
stealth_rms = np.sqrt(np.mean(rx_signal[int(fs*1.5):]**2))
reduction = (1 - (stealth_rms / normal_rms)) * 100

print(f"\n--- ANALYSIS ---")
print(f"Normal Volume: {normal_rms:.4f}")
print(f"Stealth Volume: {stealth_rms:.4f}")
print(f"Total Noise Reduction: {reduction:.2f}%")