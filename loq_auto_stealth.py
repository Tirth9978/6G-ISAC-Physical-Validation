import numpy as np
import sounddevice as sd
import matplotlib.pyplot as plt

# --- 1. HARDWARE CONFIGURATION ---
MIC_ID = 1
SPEAKER_ID = 5
fs = 48000
sd.default.device = (MIC_ID, SPEAKER_ID)

print("--- LENOVO LOQ: AUTO-CALIBRATING STEALTH SYSTEM ---")
print("Step 1: Scanning for the Physical Null Point...")

# --- 2. PHASE SWEEP (FIND THE MAGIC NUMBER) ---
duration_sweep = 8.0  # 8 second scan
f0 = 10000.0         # 10 kHz calibration tone
t_sweep = np.linspace(0, duration_sweep, int(fs * duration_sweep), endpoint=False)

left_sweep = 0.5 * np.sin(2 * np.pi * f0 * t_sweep)
phase_shift_array = np.linspace(0, 2 * np.pi, len(t_sweep))
right_sweep = 0.5 * np.sin((2 * np.pi * f0 * t_sweep) + phase_shift_array)

tx_sweep = np.column_stack((left_sweep, right_sweep))
rx_sweep = sd.playrec(tx_sweep, samplerate=fs, channels=1, blocking=True).flatten()

# Analyze Sweep
window_size = int(fs * 0.05)
num_windows = len(rx_sweep) // window_size
volume_envelope = np.zeros(num_windows)
degrees_axis = np.zeros(num_windows)

for i in range(num_windows):
    start = i * window_size
    end = start + window_size
    volume_envelope[i] = np.sqrt(np.mean(rx_sweep[start:end]**2))
    degrees_axis[i] = (phase_shift_array[start] / (2 * np.pi)) * 360

best_phase = degrees_axis[np.argmin(volume_envelope)]
print(f"SUCCESS: Physical Null found at {best_phase:.2f} degrees.")

# --- 3. STEALTH DATA TEST (USE THE DISCOVERED NULL) ---
print(f"Step 2: Executing Stealth Test using {best_phase:.2f}°...")

T_msg = 1.0 
t_msg = np.linspace(0, T_msg, int(fs * T_msg), endpoint=False)
MESSAGE = "Hi"
binary_msg = ''.join(format(ord(i), '08b') for i in MESSAGE)

data_signal = np.zeros_like(t_msg)
samples_per_bit = len(data_signal) // len(binary_msg)
for i, bit in enumerate(binary_msg):
    start = i * samples_per_bit
    end = start + samples_per_bit
    data_signal[start:end] = np.sin(2 * np.pi * f0 * t_msg[start:end]) if bit == '1' else -np.sin(2 * np.pi * f0 * t_msg[start:end])

# Normal Case
normal_tx = np.column_stack((data_signal, data_signal))

# Stealth Case (Using Discovered Null)
phase_rad = np.radians(best_phase)
stealth_right = np.sin((2 * np.pi * f0 * t_msg) + phase_rad)
stealth_right = np.where(data_signal > 0, stealth_right, -stealth_right)
stealth_tx = np.column_stack((data_signal, stealth_right))

full_tx = np.vstack((normal_tx, np.zeros((int(fs * 0.5), 2)), stealth_tx))
rx_stealth = sd.playrec(full_tx, samplerate=fs, channels=1, blocking=True).flatten()

# --- 4. ANALYSIS & PLOTTING ---
normal_rms = np.sqrt(np.mean(rx_stealth[:fs]**2))
stealth_rms = np.sqrt(np.mean(rx_stealth[int(fs*1.5):]**2))
reduction = (1 - (stealth_rms / normal_rms)) * 100

print(f"\n--- FINAL RESULTS ---")
print(f"Discovered Null: {best_phase:.2f}°")
print(f"Noise Reduction: {reduction:.2f}%")

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

# Plot 1: The Sweep Result
ax1.plot(degrees_axis, volume_envelope, color='indigo')
ax1.axvline(x=best_phase, color='red', linestyle='--', label=f'Best Null: {best_phase:.1f}°')
ax1.set_title("Part 1: Environmental Phase Calibration Scan")
ax1.set_xlabel("Phase Shift (Degrees)")
ax1.set_ylabel("Volume")
ax1.legend()

# Plot 2: The Stealth Comparison
ax2.plot(rx_stealth, color='darkorange', alpha=0.7)
ax2.axvline(x=fs*1.0, color='black', linestyle='--')
ax2.axvline(x=fs*1.5, color='black', linestyle='--')
ax2.text(fs*0.5, np.max(rx_stealth), "NORMAL", ha='center', weight='bold')
ax2.text(fs*2.0, np.max(rx_stealth), "STEALTH", ha='center', weight='bold')
ax2.set_title(f"Part 2: Real-time Interference Cancellation ({reduction:.1f}% Reduction)")
ax2.set_ylabel("Mic Amplitude")

plt.tight_layout()
plt.show()