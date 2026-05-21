import numpy as np
import sounddevice as sd
from scipy.signal import chirp, correlate
import serial
import time
import matplotlib.pyplot as plt

print("--- ISAC N-TRIAL AUTOMATED SUITE ---")

# --- 1. ARDUINO THERMODYNAMIC CALIBRATION ---
try:
    com_port = "COM17"
    print("Connecting to Arduino...")
    ser = serial.Serial(com_port, 9600, timeout=3)
    time.sleep(2) # Wait for Arduino to reset
    ser.reset_input_buffer()
    
    # Read until we get a valid temp
    temp_c = 31.64 # Fallback
    for _ in range(5):
        line = ser.readline().decode('utf-8').strip()
        if "Temperature" in line or "TEMP" in line:
            temp_c = float(''.join(c for c in line if c.isdigit() or c == '.'))
            break
    ser.close()
    
    SPEED_OF_SOUND = 331.3 + (0.606 * temp_c)
    print(f"SUCCESS: Temp = {temp_c:.2f}°C | Speed of Sound = {SPEED_OF_SOUND:.2f} m/s")
    
except Exception as e:
    print(f"Failed to connect to Arduino: {e}")
    print("Using default calibration (349.9 m/s).")
    SPEED_OF_SOUND = 349.9

# --- 2. AUDIO SETUP ---
print("\n" + str(sd.query_devices()))
in_device = int(input("Enter Laptop Mic ID: "))
out_device = int(input("Enter SoundDrum ID: "))
sd.default.device = (in_device, out_device)

T = float(input("\nEnter Pulse Duration (e.g., 0.1 or 0.05): "))
target_dist = float(input("Enter Physical Target Distance in meters (e.g., 2.0 or 6.0): "))
num_trials = int(input("Enter Number of Trials (N) (e.g., 10): "))

fs = 44100
MESSAGE = "Hi"
binary_msg = ''.join(format(ord(i), '08b') for i in MESSAGE)

# --- TIMING BUFFERS ---
warmup_duration = 1.0   
listen_duration = 2.0   
cooldown_duration = 1.5 

t_pulse = np.linspace(0, T, int(fs * T))
f0, f1 = 8000, 12000
radar_chirp = chirp(t_pulse, f0=f0, f1=f1, t1=T, method='linear')

# EFIM Generation (Stage 3)
data_signal = np.zeros_like(radar_chirp)
samples_per_bit = len(data_signal) // len(binary_msg)
for i, bit in enumerate(binary_msg):
    start = i * samples_per_bit
    end = start + samples_per_bit
    if bit == '1':
        data_signal[start:end] = np.sin(2 * np.pi * 10000 * t_pulse[start:end])
    else:
        data_signal[start:end] = -np.sin(2 * np.pi * 10000 * t_pulse[start:end])

tx_combined = radar_chirp + (data_signal * 0.5)

# --- ANTI-POP FADE ENVELOPE ---
fade_len = int(fs * 0.01) 
if fade_len < len(tx_combined) / 2: 
    tx_combined[:fade_len] *= np.linspace(0, 1, fade_len)
    tx_combined[-fade_len:] *= np.linspace(1, 0, fade_len)

tx_full = np.concatenate((
    np.zeros(int(fs * warmup_duration)), 
    tx_combined, 
    np.zeros(int(fs * listen_duration)),
    np.zeros(int(fs * cooldown_duration))
))

def get_distance(corr_array, sync_idx, window_size):
    MIN_SEARCH_DISTANCE = 0.25 
    min_search_samples = int(fs * ((MIN_SEARCH_DISTANCE * 2.0) / SPEED_OF_SOUND))
    
    start_idx = sync_idx + min_search_samples
    end_idx = min(sync_idx + window_size, len(corr_array))
    
    if start_idx >= end_idx: return 0.0
        
    search_window = corr_array[start_idx : end_idx]
    echo_idx = np.argmax(np.abs(search_window)) + min_search_samples
    time_delay = echo_idx / fs
    return (time_delay * SPEED_OF_SOUND) / 2.0

# --- 3. N-TRIAL LOOP ---
results_efim = []
print(f"\n--- STARTING {num_trials} TRIALS ---")

MAX_SEARCH_DISTANCE = 15.0 
search_window_samples = int(fs * ((MAX_SEARCH_DISTANCE * 2.0) / SPEED_OF_SOUND))

for trial in range(1, num_trials + 1):
    print(f"Running Trial {trial}/{num_trials}...")
    rx_signal = sd.playrec(tx_full, samplerate=fs, channels=1, blocking=True).flatten()
    
    corr_sync = correlate(rx_signal, tx_combined, mode='valid')
    sync_idx = np.argmax(np.abs(corr_sync))
    
    received_pulse = rx_signal[sync_idx : sync_idx + len(tx_combined)]
    if len(received_pulse) < len(tx_combined):
        received_pulse = np.pad(received_pulse, (0, len(tx_combined) - len(received_pulse)))
    
    reconstructed_data = data_signal * 0.5 
    filtered_rx = received_pulse - reconstructed_data 
    corr_efim = correlate(rx_signal, filtered_rx, mode='full')
    
    dist_efim = get_distance(corr_efim, sync_idx, search_window_samples)
    results_efim.append(dist_efim)
    time.sleep(1)

# --- 4. STATISTICAL ANALYSIS & GRAPHING ---
mean_dist = np.mean(results_efim)
std_dev = np.std(results_efim)
mean_error = abs(target_dist - mean_dist)

print("\n=== EXPERIMENT COMPLETE ===")
print(f"Pulse: {T}s | Target: {target_dist}m")
print(f"Mean Measured: {mean_dist:.2f} m | Std Dev: {std_dev:.3f} m")

# Save to Log
with open(f"ISAC_Stats_{target_dist}m_{T}s.txt", "w") as f:
    f.write(f"--- {num_trials}-TRIAL ISAC STATS ---\n")
    f.write(f"Target: {target_dist}m | Pulse: {T}s | Speed: {SPEED_OF_SOUND:.2f} m/s\n\n")
    for idx, val in enumerate(results_efim): f.write(f"Trial {idx+1}: {val:.3f} m\n")
    f.write(f"\nMean: {mean_dist:.3f} m | Std Dev: {std_dev:.3f} m | Error: {mean_error*100:.1f} cm\n")

# --- PLOT GENERATION ---
plt.figure(figsize=(8, 5))
trials_axis = range(1, num_trials + 1)
plt.plot(trials_axis, results_efim, marker='o', linestyle='-', color='#0055a4', label='Measured Distance')
plt.axhline(y=target_dist, color='r', linestyle='--', label=f'True Distance ({target_dist}m)')
plt.axhline(y=mean_dist, color='g', linestyle='-.', label=f'Mean ({mean_dist:.2f}m)')
plt.fill_between(trials_axis, mean_dist - std_dev, mean_dist + std_dev, color='g', alpha=0.15, label='±1 Std Dev')

plt.title(f"ISAC Ranging Results ({num_trials} Trials, Pulse: {T}s)")
plt.xlabel("Trial Number")
plt.ylabel("Calculated Distance (m)")
plt.ylim(0, min(MAX_SEARCH_DISTANCE, max(results_efim)*1.2))
plt.legend()
plt.grid(True, linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig(f"ISAC_Graph_{target_dist}m_{T}s.png", dpi=300)
plt.show()