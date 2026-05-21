import numpy as np
import sounddevice as sd
from scipy.signal import chirp, correlate
import serial
import time
import matplotlib.pyplot as plt

print("--- PURE SENSING: N-TRIAL AUTOMATED SUITE ---")

# --- 1. ARDUINO THERMODYNAMIC CALIBRATION ---
try:
    com_port = "COM17"
    ser = serial.Serial(com_port, 9600, timeout=3)
    time.sleep(2)
    ser.reset_input_buffer()
    
    temp_c = 31.64
    for _ in range(5):
        line = ser.readline().decode('utf-8').strip()
        if "Temperature" in line or "TEMP" in line:
            temp_c = float(''.join(c for c in line if c.isdigit() or c == '.'))
            break
    ser.close()
    SPEED_OF_SOUND = 331.3 + (0.606 * temp_c)
    print(f"SUCCESS: Temp = {temp_c:.2f}°C | Speed of Sound = {SPEED_OF_SOUND:.2f} m/s")
except Exception:
    print("Using default calibration (349.9 m/s).")
    SPEED_OF_SOUND = 349.9

# --- 2. AUDIO SETUP ---
in_device = int(input("Enter Laptop Mic ID: "))
out_device = int(input("Enter SoundDrum ID: "))
sd.default.device = (in_device, out_device)
target_dist = float(input("\nEnter Physical Target Distance in meters: "))
num_trials = int(input("Enter Number of Trials (N) (e.g., 10): "))

fs = 44100  
warmup_duration = 1.0   
pulse_duration = 0.1    
listen_duration = 2.0   
cooldown_duration = 1.5 

t_pulse = np.linspace(0, pulse_duration, int(fs * pulse_duration))
base_chirp = chirp(t_pulse, f0=8000, f1=12000, t1=pulse_duration, method='linear')

fade_len = int(fs * 0.01)
if fade_len < len(base_chirp) / 2:
    base_chirp[:fade_len] *= np.linspace(0, 1, fade_len)
    base_chirp[-fade_len:] *= np.linspace(1, 0, fade_len)

tx_full = np.concatenate((
    np.zeros(int(fs * warmup_duration)), 
    base_chirp, 
    np.zeros(int(fs * listen_duration)),
    np.zeros(int(fs * cooldown_duration))
))

# --- 3. N-TRIAL LOOP ---
results_radar = []
MAX_SEARCH_DISTANCE = 15.0 
search_window_samples = int(fs * ((MAX_SEARCH_DISTANCE * 2.0) / SPEED_OF_SOUND))

MIN_SEARCH_DISTANCE = 0.25 
min_search_samples = int(fs * ((MIN_SEARCH_DISTANCE * 2.0) / SPEED_OF_SOUND))

print(f"\n--- STARTING {num_trials} TRIALS ---")
for trial in range(1, num_trials + 1):
    print(f"Running Trial {trial}/{num_trials}...")
    rx_signal = sd.playrec(tx_full, samplerate=fs, channels=1, blocking=True).flatten()
    
    corr_sync = correlate(rx_signal, base_chirp, mode='valid')
    sync_idx = np.argmax(np.abs(corr_sync))
    
    start_idx = sync_idx + min_search_samples
    end_idx = min(sync_idx + search_window_samples, len(corr_sync))
    
    if start_idx < end_idx:
        search_window = corr_sync[start_idx : end_idx]
        echo_idx = np.argmax(np.abs(search_window)) + min_search_samples
        time_delay = echo_idx / fs
        dist = (time_delay * SPEED_OF_SOUND) / 2.0
        results_radar.append(dist)
    time.sleep(1)

# --- 4. STATISTICAL LOGGING & GRAPHING ---
mean_dist = np.mean(results_radar)
std_dev = np.std(results_radar)
mean_error = abs(target_dist - mean_dist)

print("\n=== EXPERIMENT COMPLETE ===")
print(f"Mean Measured: {mean_dist:.2f} m | Std Dev: {std_dev:.3f} m | Error: {mean_error*100:.1f} cm")

with open(f"Radar_Stats_{target_dist}m.txt", "w") as f:
    f.write(f"--- {num_trials}-TRIAL PURE RADAR STATS ---\n")
    f.write(f"Target: {target_dist}m | Speed: {SPEED_OF_SOUND:.2f} m/s\n\n")
    for idx, val in enumerate(results_radar): f.write(f"Trial {idx+1}: {val:.3f} m\n")
    f.write(f"\nMean: {mean_dist:.3f} m | Std Dev: {std_dev:.3f} m | Mean Error: {mean_error*100:.1f} cm\n")

# --- PLOT GENERATION ---
plt.figure(figsize=(8, 5))
trials_axis = range(1, num_trials + 1)
plt.plot(trials_axis, results_radar, marker='o', linestyle='-', color='indigo', label='Measured Distance')
plt.axhline(y=target_dist, color='r', linestyle='--', label=f'True Distance ({target_dist}m)')
plt.axhline(y=mean_dist, color='g', linestyle='-.', label=f'Mean ({mean_dist:.2f}m)')
plt.fill_between(trials_axis, mean_dist - std_dev, mean_dist + std_dev, color='g', alpha=0.15, label='±1 Std Dev')

plt.title(f"Pure Radar Ranging Results ({num_trials} Trials, Target: {target_dist}m)")
plt.xlabel("Trial Number")
plt.ylabel("Calculated Distance (m)")
plt.ylim(0, min(MAX_SEARCH_DISTANCE, max(results_radar)*1.2))
plt.legend()
plt.grid(True, linestyle='--', alpha=0.7)
plt.tight_layout()
plt.savefig(f"Radar_Graph_{target_dist}m.png", dpi=300)
plt.show()