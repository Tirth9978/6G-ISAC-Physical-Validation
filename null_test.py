import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt

print("--- LENOVO LOQ: ELECTRONIC NULL SWEEP ---")
print("WARNING: Unplug headphones. Ensure Windows Audio Enhancements are OFF.")
print(sd.query_devices())

# in_device = int(input("\nEnter LOQ Built-in Mic ID: "))
# out_device = int(input("Enter LOQ Built-in Speakers ID: "))
in_device = 1
out_device = 5
sd.default.device = (in_device, out_device)

fs = 48000
duration = 10.0  # 10 second sweep
f0 = 10000.0     # 10 kHz test tone

print(f"\nGenerating a {duration} second phase sweep...")
t = np.linspace(0, duration, int(fs * duration), endpoint=False)

# Left Speaker: Constant 10kHz Sine Wave (+Data)
left_channel = 0.5 * np.sin(2 * np.pi * f0 * t)

# Right Speaker: Shifting Phase from 0 to 360 degrees (0 to 2*PI)
# This electronically "moves" the null zone across your screen!
phase_shift_array = np.linspace(0, 2 * np.pi, len(t))
right_channel = 0.5 * np.sin((2 * np.pi * f0 * t) + phase_shift_array)

# Combine into Stereo
tx_stereo = np.column_stack((left_channel, right_channel))

print("FIRING SPEAKERS. Keep perfectly still. Do not type or move...")
# Play out of stereo speakers, record from mono webcam mic
rx_signal = sd.playrec(tx_stereo, samplerate=fs, channels=1, blocking=True).flatten()

print("Analyzing microphone telemetry...")

# Calculate the Volume (Amplitude Envelope) over time
# We use a moving RMS (Root Mean Square) window to see how loud the mic was
window_size = int(fs * 0.05) # 50 millisecond chunks
num_windows = len(rx_signal) // window_size
volume_envelope = np.zeros(num_windows)
degrees_axis = np.zeros(num_windows)

for i in range(num_windows):
    start = i * window_size
    end = start + window_size
    chunk = rx_signal[start:end]
    # RMS calculates the "loudness" of the chunk
    volume_envelope[i] = np.sqrt(np.mean(chunk**2))
    # Map this chunk to the corresponding phase angle in degrees
    degrees_axis[i] = (phase_shift_array[start] / (2 * np.pi)) * 360

# --- VISUALIZE THE NULL ---
plt.figure(figsize=(10, 5))
plt.plot(degrees_axis, volume_envelope, color='indigo', linewidth=2)

# Find the exact degree where the mic was quietest
min_vol_idx = np.argmin(volume_envelope)
best_phase = degrees_axis[min_vol_idx]

plt.axvline(x=best_phase, color='red', linestyle='--', label=f'Perfect Null at {best_phase:.1f}°')
plt.title("Acoustic Spatial Nulling (Lenovo LOQ Chassis)")
plt.xlabel("Phase Shift of Right Speaker (Degrees)")
plt.ylabel("Microphone Received Volume (Amplitude)")
plt.annotate('Destructive Interference\n(The Dead Zone)', 
             xy=(best_phase, volume_envelope[min_vol_idx]), 
             xytext=(best_phase + 20, np.max(volume_envelope)*0.8),
             arrowprops=dict(facecolor='black', shrink=0.05))

plt.grid(True, linestyle='--', alpha=0.7)
plt.legend()
plt.tight_layout()
plt.show()