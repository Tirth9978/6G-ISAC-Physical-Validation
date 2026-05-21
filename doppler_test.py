import numpy as np
import sounddevice as sd
import serial
import time
import matplotlib.pyplot as plt

print("--- DOPPLER N-TRIAL AUTOMATED SUITE ---")

try:
    com_port = "COM17"
    ser = serial.Serial(com_port, 9600, timeout=3)
    time.sleep(2)
    ser.reset_input_buffer()
    temp_c = 31.64
    for _ in range(5):
        line = ser.readline().decode('utf-8').strip()
        if line.startswith("TEMP:"):
            temp_c = float(line.split(":")[1])
            break
    ser.close()
    SPEED_OF_SOUND = 331.3 + (0.606 * temp_c)
    print(f"Calibrated: {temp_c:.2f}°C | {SPEED_OF_SOUND:.2f} m/s")
except Exception:
    print("Using default calibration (349.9 m/s).")
    SPEED_OF_SOUND = 349.9

in_device = int(input("Enter Laptop Mic ID: "))
out_device = int(input("Enter SoundDrum ID: "))
sd.default.device = (in_device, out_device)
num_trials = int(input("Enter Number of Trials (N) (e.g., 10): "))

# --- TIMING & SIGNAL SETUP ---
fs = 44100
warmup_duration = 1.0   
tone_duration = 2.5     
cooldown_duration = 1.5 
f0 = 10000.0           

t_tone = np.linspace(0, tone_duration, int(fs * tone_duration))
raw_tone = 0.5 * np.sin(2 * np.pi * f0 * t_tone)

fade_len = int(fs * 0.01)
raw_tone[:fade_len] *= np.linspace(0, 1, fade_len)
raw_tone[-fade_len:] *= np.linspace(1, 0, fade_len)

tx_signal = np.concatenate((
    np.zeros(int(fs * warmup_duration)), 
    raw_tone, 
    np.zeros(int(fs * cooldown_duration))
))

results_speed = []
print(f"\n--- STARTING {num_trials} TRIALS. TELL TARGET TO START WALKING ---")

for trial in range(1, num_trials + 1):
    print(f"Capturing Trial {trial}/{num_trials}...")
    rx_signal = sd.playrec(tx_signal, samplerate=fs, channels=1, blocking=True).flatten()
    
    fft_spectrum = np.fft.fft(rx_signal)
    freqs = np.fft.fftfreq(len(rx_signal), 1/fs)
    
    valid_indices = np.where((freqs > 9900) & (freqs < 10100))
    peak_idx = np.argmax(np.abs(fft_spectrum[valid_indices]))
    peak_freq = freqs[valid_indices][peak_idx]
    
    shift = peak_freq - f0
    speed = (shift * SPEED_OF_SOUND) / (2 * f0)
    
    if speed > 0.1: 
        results_speed.append(speed)
    time.sleep(0.5)

# --- STATISTICAL LOGGING & GRAPHING ---
if len(results_speed) > 0:
    mean_speed = np.mean(results_speed)
    std_speed = np.std(results_speed)
    print("\n=== DOPPLER STATS ===")
    print(f"Mean Velocity: {mean_speed:.2f} m/s | Std Dev: {std_speed:.3f} m/s")
    
    with open("Doppler_Stats.txt", "w") as f:
        f.write(f"--- {len(results_speed)}-TRIAL DOPPLER STATS ---\n")
        f.write(f"Speed of Sound: {SPEED_OF_SOUND:.2f} m/s\n\n")
        for idx, val in enumerate(results_speed): f.write(f"Trial {idx+1}: {val:.3f} m/s\n")
        f.write(f"\nMean Velocity: {mean_speed:.3f} m/s | Std Dev: {std_speed:.3f} m/s\n")

    # --- PLOT GENERATION ---
    plt.figure(figsize=(8, 5))
    trials_axis = range(1, len(results_speed) + 1)
    plt.plot(trials_axis, results_speed, marker='o', linestyle='-', color='purple', label='Measured Speed')
    plt.axhline(y=mean_speed, color='g', linestyle='-.', label=f'Mean ({mean_speed:.2f} m/s)')
    plt.fill_between(trials_axis, mean_speed - std_speed, mean_speed + std_speed, color='g', alpha=0.15, label='±1 Std Dev')

    plt.title(f"Doppler Tracking Results ({len(results_speed)} Valid Trials)")
    plt.xlabel("Trial Number")
    plt.ylabel("Calculated Velocity (m/s)")
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig("Doppler_Graph.png", dpi=300)
    plt.show()
else:
    print("No valid movement data captured to save.")