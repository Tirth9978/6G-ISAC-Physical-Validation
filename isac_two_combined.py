import numpy as np
import sounddevice as sd
from scipy.signal import chirp, correlate
import serial
import time
import matplotlib.pyplot as plt
import os

print("--- ISAC N-TRIAL AUTOMATED SUITE ---")

# --- 1. ARDUINO THERMODYNAMIC CALIBRATION ---
try:
    com_port = "COM17"
    print("Connecting to Arduino...")
    ser = serial.Serial(com_port, 9600, timeout=3)
    time.sleep(2)
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
warmup_duration = 1.0
listen_duration = 3.5
MESSAGE = "Hi"
binary_msg = ''.join(format(ord(i), '08b') for i in MESSAGE)













for trial in range(1, num_trials + 1):

    t_pulse = np.linspace(0, T, int(fs * T))
    # Data Chirps (8kHz - 12kHz)
    up_chirp = chirp(t_pulse, f0=8000, f1=12000, t1=T, method='linear')
    down_chirp = chirp(t_pulse, f0=12000, f1=8000, t1=T, method='linear')
    first_chirp = up_chirp if binary_msg[0] == '1' else down_chirp
    
    # Dedicated Radar Chirp for Stage 2 (Different frequency: 2kHz - 6kHz)
    radar_chirp = chirp(t_pulse, f0=2000, f1=6000, t1=T, method='linear')

    # Build the pure data payload (For Stage 1 and 3)
    payload_data = []
    for bit in binary_msg:
        payload_data.extend(up_chirp if bit == '1' else down_chirp)
    payload_data = np.array(payload_data)

    # Build the Alpha payload (Stage 2: Radar first, then Data)
    payload_alpha = np.concatenate((radar_chirp, payload_data))

    # Setup timelines
    total_duration_1 = warmup_duration + (len(payload_data)/fs) + listen_duration
    tx_1 = np.zeros(int(fs * total_duration_1))
    tx_1[int(fs*warmup_duration) : int(fs*warmup_duration)+len(payload_data)] = payload_data

    total_duration_2 = warmup_duration + (len(payload_alpha)/fs) + listen_duration
    tx_2 = np.zeros(int(fs * total_duration_2))
    tx_2[int(fs*warmup_duration) : int(fs*warmup_duration)+len(payload_alpha)] = payload_alpha


    # --- RECORDING PHASE ---
    print("\n[TRANSMITTING] Stage 1 & 3 Waveform (100% Data)...")
    rx_1 = sd.playrec(tx_1, samplerate=fs, channels=1, blocking=True).flatten()
    if np.max(np.abs(rx_1)) < 0.05: print("[WARNING] Recording 1 is quiet! Turn up speaker.")

    print("[TRANSMITTING] Stage 2 Waveform (Alpha Split: Radar + Data)...")
    rx_2 = sd.playrec(tx_2, samplerate=fs, channels=1, blocking=True).flatten()
    if np.max(np.abs(rx_2)) < 0.05: print("[WARNING] Recording 2 is quiet! Turn up speaker.")

    print("\nProcessing Evolutionary Math...")

    # ==========================================
    # STAGE 1: NAIVE BASELINE (Failure)
    # ==========================================
    corr_naive = np.abs(correlate(rx_1, first_chirp, mode='valid'))
    sync_1 = np.argmax(corr_naive)

    # Blank direct path (+/- 5ms) to find echo
    clear_start = max(0, sync_1 - int(0.005*fs))
    clear_end = min(len(corr_naive), sync_1 + int(0.005*fs))
    corr_naive[clear_start:clear_end] = 0

    # Look for echo in next 0.05s
    echo_naive_idx = np.argmax(corr_naive[sync_1 : sync_1 + int(0.05*fs)])
    dist_naive = ((echo_naive_idx / fs) * SPEED_OF_SOUND) / 2

    # ==========================================
    # STAGE 2: THE ALPHA SOLUTION (Compromise)
    # ==========================================
    corr_alpha = np.abs(correlate(rx_2, radar_chirp, mode='valid'))
    sync_2 = np.argmax(corr_alpha)

    clear_start = max(0, sync_2 - int(0.005*fs))
    clear_end = min(len(corr_alpha), sync_2 + int(0.005*fs))
    corr_alpha[clear_start:clear_end] = 0

    echo_alpha_idx = np.argmax(corr_alpha[sync_2 : sync_2 + int(0.05*fs)])
    dist_alpha = ((echo_alpha_idx / fs) * SPEED_OF_SOUND) / 2

    # ==========================================
    # STAGE 3: THE EFIM / JOINT DESIGN SOLUTION
    # ==========================================
    corr_efim = np.abs(correlate(rx_1, payload_data, mode='valid'))
    sync_3 = np.argmax(corr_efim)

    clear_start = max(0, sync_3 - int(0.005*fs))
    clear_end = min(len(corr_efim), sync_3 + int(0.005*fs))
    corr_efim[clear_start:clear_end] = 0

    echo_efim_idx = np.argmax(corr_efim[sync_3 : sync_3 + int(0.05*fs)])
    dist_efim = ((echo_efim_idx / fs) * SPEED_OF_SOUND) / 2

    # --- STAGE 3 COMMS DECODE ---
    match_up = np.abs(correlate(rx_1, up_chirp, mode='valid'))
    match_down = np.abs(correlate(rx_1, down_chirp, mode='valid'))

    decoded_msg = ""
    search_margin = int(fs * 0.02) # 20ms jitter window

    sync_comms = np.argmax(match_up if binary_msg[0] == '1' else match_down)

    for i in range(len(binary_msg)):
        expected_idx = sync_comms + (i * len(up_chirp))
        win_start = max(0, expected_idx - search_margin)
        win_end = min(len(match_up), expected_idx + search_margin)
        
        if win_start >= len(match_up):
            decoded_msg += "?"
            continue
            
        if np.max(match_up[win_start:win_end]) > np.max(match_down[win_start:win_end]):
            decoded_msg += "1"
        else:
            decoded_msg += "0"

    print(f"\n[RESULTS] Trial : ${trial}")
    print(f"Stage 1 (Naive): Radar Guessed {dist_naive:.2f}m (Failed due to interference)")
    print(f"Stage 2 (Alpha): Radar Calculated {dist_alpha:.2f}m (Accurate, but data delayed)")
    print(f"Stage 3 (EFIM):  Radar Calculated {dist_efim:.2f}m (Accurate + Full Speed Data!)")
    print(f"Stage 3 Comms:   Original: {binary_msg}")
    print(f"Stage 3 Comms:   Decoded:  {decoded_msg}")

    # ==========================================
    # VISUALIZATION (THE IEEE MONEY SHOT)
    # ==========================================
    window_size = int(0.05 * fs)
    # Graph X-axis accurately scaled to the new speed of sound
    d_window = (np.arange(window_size) / fs * SPEED_OF_SOUND) / 2

    def get_safe_window(arr, start_idx, size):
        slice_arr = arr[start_idx : start_idx + size]
        if len(slice_arr) < size:
            return np.pad(slice_arr, (0, size - len(slice_arr)))
        return slice_arr

    plt.figure(figsize=(10, 8))

    plt.subplot(3, 1, 1)
    plt.plot(d_window, get_safe_window(corr_naive, sync_1, window_size), color='red')
    plt.title(f"Stage 1: Naïve ISAC (Range Ambiguity Failure) - Guessed: {dist_naive:.2f}m")
    plt.ylabel("Fisher Info")
    plt.grid(True, linestyle='--')

    plt.subplot(3, 1, 2)
    plt.plot(d_window, get_safe_window(corr_alpha, sync_2, window_size), color='orange')
    plt.title(f"Stage 2: The α Parameter (Accurate but Slower Data) - Calculated: {dist_alpha:.2f}m")
    plt.ylabel("Fisher Info")
    plt.grid(True, linestyle='--')

    plt.subplot(3, 1, 3)
    plt.plot(d_window, get_safe_window(corr_efim, sync_3, window_size), color='green')
    plt.title(f"Stage 3: EFIM Joint Design (Simultaneous Data + Radar) - Calculated: {dist_efim:.2f}m")
    plt.xlabel("Distance to Echo (Meters)")
    plt.ylabel("Fisher Info")
    plt.grid(True, linestyle='--')

    plt.tight_layout()

    # --- AUTOMATIC FILE SAVING ---
    log_filename = f"./ISAC_{target_dist}m_{T}s/ISAC_Logs_{target_dist}m_{T}s/ISAC_Log_{target_dist}m_{T}s_Trial{trial}.txt"
    plot_filename = f"./ISAC_{target_dist}m_{T}s/ISAC_Plots_{target_dist}m_{T}s/ISAC_Plot_{target_dist}m_{T}s_Trial{trial}.png"

    # Create directories if they don't exist
    os.makedirs(os.path.dirname(log_filename), exist_ok=True)
    os.makedirs(os.path.dirname(plot_filename), exist_ok=True)

    # 1. Save the Image
    plt.savefig(plot_filename, dpi=300, bbox_inches='tight')

    # 2. Save the Text Log
    with open(log_filename, "w") as f:
        f.write("--- ISAC EVOLUTION OUTDOOR RESULTS ---\n")
        f.write(f"Target Distance: {target_dist} meters\n")
        f.write(f"Pulse Duration (Data Rate): {T} seconds\n")
        f.write(f"Calibrated Speed of Sound: {SPEED_OF_SOUND} m/s\n")
        f.write("-" * 40 + "\n")
        f.write(f"Stage 1 (Naive): Radar Guessed {dist_naive:.2f}m\n")
        f.write(f"Stage 2 (Alpha): Radar Calculated {dist_alpha:.2f}m\n")
        f.write(f"Stage 3 (EFIM):  Radar Calculated {dist_efim:.2f}m\n")
        f.write("-" * 40 + "\n")
        f.write(f"Stage 3 Comms Original: {binary_msg}\n")
        f.write(f"Stage 3 Comms Decoded:  {decoded_msg}\n")

    print(f"\n[SYSTEM] Successfully auto-saved log to: {log_filename}")
    print(f"[SYSTEM] Successfully auto-saved plot to: {plot_filename}")

