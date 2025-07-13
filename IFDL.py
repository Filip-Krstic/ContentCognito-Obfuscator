import os
import csv
import time
import random
import threading
import subprocess
import logging
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Tuple

import pyautogui
import pygetwindow as gw
from PIL import Image

import torch
import numpy as np
from transformers import CLIPProcessor, CLIPModel

# === CONFIGURATION === #
# File to store counts of detected labels
LABEL_COUNT_FILE: str = "label_counts.csv"
# Title of the Scrcpy mirror window
SCRCPY_WINDOW_TITLE: str = "Scrcpy_Mirror_Window"

# === INITIALIZE LOGGING === #
# Configure basic logging for informational messages
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

# === GLOBAL VARIABLES FOR GUI AND THREAD CONTROL === #
# Event flag to control the execution of long-running threads (scheduler, ADB keep-alive)
running_event: threading.Event = threading.Event()
# Reference to the main scheduling thread
scheduler_thread: Optional[threading.Thread] = None
# Reference to the Scrcpy subprocess
adb_process: Optional[subprocess.Popen] = None

# === LOAD AI MODEL === #
logging.info("Loading CLIP model for image classification...")
# Load pre-trained CLIP model and processor
model = CLIPModel.from_pretrained("openai/clip-vit-base-patch16")
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch16")

# === ADB UTILITIES === #
def run_adb_command(cmd: List[str]) -> str:
    """
    Executes an ADB command and returns its standard output.

    Args:
        cmd: A list of strings representing the ADB command and its arguments.

    Returns:
        The stripped standard output of the command, or an empty string if an error occurs.
    """
    try:
        result = subprocess.run(["adb"] + cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error(f"ADB command failed: {' '.join(e.cmd)}, Error: {e.stderr.strip()}")
        return ""
    except FileNotFoundError:
        messagebox.showerror("Error", "ADB not found. Please ensure ADB is installed and in your system's PATH.")
        logging.error("ADB executable not found. Please ensure ADB is installed and in your system's PATH.")
        return ""

def get_screen_size() -> Tuple[int, int]:
    """
    Detects the connected Android device's screen size using ADB.

    Returns:
        A tuple containing the screen width and height (e.g., (1080, 1920)).
        Defaults to (1080, 1920) if detection fails.
    """
    output = run_adb_command(["shell", "wm", "size"])
    if "Physical size:" in output:
        size_str = output.split("Physical size:")[-1].strip()
        try:
            width, height = map(int, size_str.split("x"))
            return width, height
        except ValueError:
            logging.error(f"Failed to parse screen size: {size_str}")
            return 1080, 1920 # Fallback
    else:
        logging.error("Could not detect screen size. Ensure device is connected and ADB is working correctly.")
        return 1080, 1920 # Default to common size if detection fails

# Determine screen dimensions once at startup
SCREEN_WIDTH, SCREEN_HEIGHT = get_screen_size()

def keep_adb_alive() -> None:
    """
    Periodically runs a simple ADB command to maintain the ADB server connection.
    This prevents the connection from timing out during long periods of inactivity.
    """
    while running_event.is_set():
        run_adb_command(["devices"])  # A lightweight command to keep the connection active
        time.sleep(30)  # Check every 30 seconds

# === DEVICE CONTROL FUNCTIONS === #
def turn_on_screen() -> None:
    """Turns on the Android device's screen and attempts a swipe-to-unlock."""
    logging.info("Turning on screen...")
    run_adb_command(["shell", "input", "keyevent", "26"])  # KEYCODE_POWER to wake up
    time.sleep(1)
    # Attempt a swipe up to dismiss simple lock screens (e.g., no PIN/pattern)
    run_adb_command(["shell", "input", "keyevent", "82"])  # KEYCODE_MENU (often acts as unlock)
    time.sleep(1)

def swipe_to_unlock() -> None:
    """Performs a generic swipe gesture to unlock the device."""
    logging.info("Performing swipe to unlock...")
    # Swipe from bottom-middle to top-middle
    run_adb_command(["shell", "input", "swipe", "300", "1000", "300", "500", "100"])
    time.sleep(1)

def enter_pin(pin: str) -> None:
    """
    Enters the specified PIN code on the device.

    Args:
        pin: The PIN code as a string.
    """
    logging.info("Entering PIN...")
    run_adb_command(["shell", "input", "text", pin])
    time.sleep(0.5)
    run_adb_command(["shell", "input", "keyevent", "66"])  # KEYCODE_ENTER
    time.sleep(0.5)

def turn_off_screen() -> None:
    """Turns off the Android device's screen."""
    logging.info("Turning off screen...")
    run_adb_command(["shell", "input", "keyevent", "26"])  # KEYCODE_POWER to turn off

def unlock_device(pin_code: str, unlock_method: str) -> None:
    """
    Unlocks the device based on the specified method.

    Args:
        pin_code: The PIN code if 'pin' method is chosen.
        unlock_method: The chosen unlock method ('pin' or 'no_pin').
    """
    logging.info(f"Attempting to unlock device with method: '{unlock_method}'...")
    turn_on_screen()
    if unlock_method == "pin" and pin_code:
        swipe_to_unlock()
        enter_pin(pin_code)
    elif unlock_method == "no_pin":
        swipe_to_unlock()  # Just swipe, assuming no PIN/pattern is required
    else:
        logging.warning("No valid unlock method selected or PIN not provided for 'pin' method.")
    time.sleep(2)  # Allow time for the unlock action to register

def delayed_screen_off(delay: int = 5) -> None:
    """
    Schedules the device screen to turn off after a specified delay.

    Args:
        delay: The delay in seconds before turning off the screen.
    """
    threading.Timer(delay, turn_off_screen).start()

# === LABEL TRACKING AND PERSISTENCE === #
def load_label_counts() -> Dict[str, int]:
    """
    Loads label detection counts from the CSV file.

    Returns:
        A dictionary where keys are labels and values are their counts.
    """
    label_counts: Dict[str, int] = {}
    if os.path.exists(LABEL_COUNT_FILE):
        try:
            with open(LABEL_COUNT_FILE, mode='r', newline='', encoding='utf-8') as file:
                reader = csv.reader(file)
                for row in reader:
                    if len(row) == 2:
                        try:
                            label_counts[row[0]] = int(row[1])
                        except ValueError:
                            logging.warning(f"Skipping malformed row in {LABEL_COUNT_FILE}: {row}")
        except IOError as e:
            logging.error(f"Error loading label counts from {LABEL_COUNT_FILE}: {e}")
    return label_counts

def save_label_counts(label_counts: Dict[str, int]) -> None:
    """
    Saves label detection counts to the CSV file.

    Args:
        label_counts: A dictionary of labels and their counts.
    """
    try:
        with open(LABEL_COUNT_FILE, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            for label, count in label_counts.items():
                writer.writerow([label, count])
    except IOError as e:
        logging.error(f"Error saving label counts to {LABEL_COUNT_FILE}: {e}")

# === AI INTERACTION LOGIC === #
# Predefined list of labels for image classification
LABELS: List[str] = [
    "love", "couple", "romantic", "kissing", "fighting", "judo", "mma", "boxing", "jiujitsu", "programming", "robotics", "pcb",
    "microcontrollers", "party", "friendship", "motorcycles", "motogp", "motocross", "couple goals", "wedding", "date", "heart",
    "affection", "intimacy", "passion", "champion", "kickboxing", "wrestling", "combat sports", "technology", "electronics",
    "automation", "mechanical engineering", "arduino", "raspberry pi", "self-driving cars", "ai", "virtual reality", "coding",
    "programmer", "developer", "guitar", "dancing", "love story", "romantic dinner", "long distance relationship",
    "relationship goals", "friends", "bachelor party", "dance floor", "nightlife", "motorcycle racing", "dirt bike",
    "off-road racing", "rally", "superbike", "rider", "helmet", "adventure sports"
]

def bounded_cauchy(center: float, scale: float, min_val: int, max_val: int) -> int:
    """
    Generates an integer value from a bounded Cauchy distribution.
    This is used to introduce realistic, non-uniform randomness for click coordinates.

    Args:
        center: The center of the distribution.
        scale: The scale parameter of the Cauchy distribution.
        min_val: The minimum allowed value.
        max_val: The maximum allowed value.

    Returns:
        A randomly generated integer within the specified bounds.
    """
    for _ in range(100):  # Attempt up to 100 times to find a value within bounds
        val = int(center + scale * np.random.standard_cauchy())
        if min_val <= val <= max_val:
            return val
    # Fallback to a clamped center value if no valid random value is found
    return max(min(int(center), max_val), min_val)

def classify_and_click(window: gw.Window, label_counts: Dict[str, int]) -> bool:
    """
    Captures a screenshot of the Scrcpy window, classifies its content using CLIP,
    and performs simulated clicks if a high-confidence label is detected.

    Args:
        window: The pygetwindow object representing the Scrcpy window.
        label_counts: A dictionary to update with detected label counts.

    Returns:
        True if a high-confidence label was detected and clicks were performed, False otherwise.
    """
    try:
        # Capture screenshot of the Scrcpy window region
        screenshot = pyautogui.screenshot(region=(window.left, window.top, window.width, window.height))
        screenshot_path = "scrcpy_window_screenshot.png"
        screenshot.save(screenshot_path)

        image = Image.open(screenshot_path)
        # Prepare inputs for the CLIP model (text labels and image)
        inputs = processor(text=LABELS, images=image, return_tensors="pt", padding=True)
        # Get model outputs (logits)
        outputs = model(**inputs)
        # Apply softmax to get probabilities
        probs = outputs.logits_per_image.softmax(dim=1)
        
        # Get the index of the label with the highest probability
        top_index = torch.argmax(probs)
        label = LABELS[top_index]
        confidence = probs[0][top_index].item()

        # If confidence is above a threshold, log and perform clicks
        if confidence > 0.51:  # Threshold can be adjusted
            logging.info(f"Detected: '{label}' (Confidence: {confidence:.2%})")
            label_counts[label] = label_counts.get(label, 0) + 1
            perform_clicks()
            return True
        return False
    except Exception as e:
        logging.error(f"Error during image classification or simulated clicking: {e}")
        return False

def perform_clicks() -> None:
    """
    Performs simulated mouse clicks within a defined region of the screen.
    Click coordinates are randomized using a bounded Cauchy distribution for natural variation.
    """
    # Define a central region for clicks
    x_center, y_center = int(SCREEN_WIDTH * 0.3), int(SCREEN_HEIGHT * 0.3)
    x_min, x_max = int(SCREEN_WIDTH * 0.15), int(SCREEN_WIDTH * 0.5)
    y_min, y_max = int(SCREEN_HEIGHT * 0.15), int(SCREEN_HEIGHT * 0.5)

    # Generate random click coordinates within bounds
    x = bounded_cauchy(x_center, SCREEN_WIDTH * 0.01, x_min, x_max)
    y = bounded_cauchy(y_center, SCREEN_HEIGHT * 0.01, y_min, y_max)

    pyautogui.moveTo(x, y)
    time.sleep(0.3)
    pyautogui.click(x, y)
    time.sleep(0.1)
    pyautogui.click(x, y)

def do_scroll() -> None:
    """
    Performs a simulated vertical scroll gesture on the device screen using ADB.
    Scroll parameters are randomized for natural interaction.
    """
    time.sleep(0.5)
    # Define scroll start and end points
    x_center = int(SCREEN_WIDTH * 0.5)
    y_start_center = int(SCREEN_HEIGHT * 0.85)
    y_end_center = int(SCREEN_HEIGHT * 0.4)

    # Define bounds for randomizing scroll coordinates
    x_min, x_max = int(SCREEN_WIDTH * 0.3), int(SCREEN_WIDTH * 0.7)
    y_min, y_max = int(SCREEN_HEIGHT * 0.3), int(SCREEN_HEIGHT * 0.95)

    # Generate random start and end coordinates for the swipe
    x1 = bounded_cauchy(x_center, SCREEN_WIDTH * 0.02, x_min, x_max)
    x2 = bounded_cauchy(x_center, SCREEN_WIDTH * 0.02, x_min, x_max)
    y1 = bounded_cauchy(y_start_center, SCREEN_HEIGHT * 0.05, y_min, y_max)
    y2 = bounded_cauchy(y_end_center, SCREEN_HEIGHT * 0.05, y_min, y_max)

    # Ensure scroll is generally downwards; adjust if y1 ends up higher than y2
    if y1 < y2:
        y2 = bounded_cauchy(y_end_center, SCREEN_HEIGHT * 0.05, y_min, y_max)

    duration = random.randint(100, 200)  # Duration of the swipe in milliseconds
    run_adb_command(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])

# === MAIN INTERACTION RUNNER === #
def run_session(duration_min: int, pin_code: str, unlock_method: str) -> None:
    """
    Executes a single automated interaction session on the device.

    Args:
        duration_min: The duration of the session in minutes.
        pin_code: The PIN code for unlocking the device.
        unlock_method: The method to unlock the device ('pin' or 'no_pin').
    """
    window = get_scrcpy_window()
    if not window:
        logging.error("Scrcpy window not found! Please ensure Scrcpy is running before starting the script.")
        messagebox.showerror("Error", "Scrcpy window not found! Please ensure Scrcpy is running.")
        return

    label_counts = load_label_counts()
    end_time = time.time() + duration_min * 60

    unlock_device(pin_code, unlock_method)  # Unlock at the start of each session

    # Main loop for the session
    while time.time() < end_time and running_event.is_set():
        found = classify_and_click(window, label_counts)
        do_scroll()
        save_label_counts(label_counts)
        # Adjust sleep time based on whether a relevant label was found
        time.sleep(random.randint(2, 17) if found else random.randint(1, 5))

    turn_off_screen()

def get_scrcpy_window() -> Optional[gw.Window]:
    """
    Attempts to find and return the Scrcpy window object.

    Returns:
        A pygetwindow.Window object if found, otherwise None.
    """
    windows = gw.getWindowsWithTitle(SCRCPY_WINDOW_TITLE)
    if windows:
        window = windows[0]
        window.restore()  # Ensure the window is visible
        window.activate() # Bring it to the foreground
        return window
    return None

# === TIME UTILITIES FOR SCHEDULING === #
def generate_random_time(start: str, end: str) -> str:
    """
    Generates a random time string (HH:MM) between a specified start and end time.

    Args:
        start: The start time in "HH:MM" format.
        end: The end time in "HH:MM" format.

    Returns:
        A randomly generated time string in "HH:MM" format.
    """
    fmt = "%H:%M"
    s = datetime.strptime(start, fmt)
    e = datetime.strptime(end, fmt)
    if e < s:  # Handle cases where the time range spans midnight (e.g., 23:00 to 00:30)
        e += timedelta(days=1)
    random_seconds = random.randint(0, int((e - s).total_seconds()))
    random_time = s + timedelta(seconds=random_seconds)
    return random_time.strftime(fmt)

def generate_school_times(code: str) -> Optional[List[str]]:
    """
    Generates a list of specific interaction times based on school type.

    Args:
        code: The school type code ('u' for University, 'h' for High School, 'p' for Primary School).

    Returns:
        A list of time strings (HH:MM) for start, end, and bedtime interactions, or None if invalid code.
    """
    if code == "u":  # University schedule
        return [generate_random_time("08:00", "09:00"),
                generate_random_time("15:00", "18:00"),
                generate_random_time("23:00", "00:30")]
    elif code == "h":  # High School schedule
        return [generate_random_time("07:30", "08:30"),
                generate_random_time("15:00", "16:00"),
                generate_random_time("21:00", "22:30")]
    elif code == "p":  # Primary School schedule
        return [generate_random_time("07:30", "08:30"),
                generate_random_time("15:00", "16:00"),
                generate_random_time("20:00", "21:00")]
    else:
        logging.error(f"Invalid school code provided: {code}")
        return None

def is_within_time(current: str, target: str, tolerance_minutes: int = 5) -> bool:
    """
    Checks if the current time is within a specified tolerance of a target time.

    Args:
        current: The current time in "HH:MM" format.
        target: The target time in "HH:MM" format.
        tolerance_minutes: The number of minutes tolerance around the target time.

    Returns:
        True if the current time is within the tolerance of the target time, False otherwise.
    """
    fmt = "%H:%M"
    current_dt = datetime.strptime(current, fmt)
    target_dt = datetime.strptime(target, fmt)
    
    # Handle target times spanning midnight for accurate comparison
    if target_dt < current_dt - timedelta(hours=12): # Target is probably next day
        target_dt += timedelta(days=1)
    elif target_dt > current_dt + timedelta(hours=12): # Target is probably previous day
        target_dt -= timedelta(days=1)

    return abs(current_dt - target_dt) <= timedelta(minutes=tolerance_minutes)

# === MAIN SCHEDULER LOOP === #
def scheduler_loop(school_type: str, pin_code: str, unlock_method: str) -> None:
    """
    The main loop that periodically checks the current time against scheduled interaction times
    and triggers interaction sessions.

    Args:
        school_type: The selected school type ('u', 'h', 'p').
        pin_code: The PIN code for unlocking the device.
        unlock_method: The method to unlock the device ('pin' or 'no_pin').
    """
    times = generate_school_times(school_type)
    if not times:
        logging.error("Scheduler could not start due to invalid school type times.")
        return

    start_time, end_time, bedtime = times
    logging.info(f"Scheduler initialized with times → Start: {start_time}, End: {end_time}, Bed: {bedtime}")
    last_activation: Optional[datetime] = None

    while running_event.is_set():
        now = datetime.now().strftime("%H:%M")

        # Regenerate daily interaction times shortly after midnight
        if "00:30" <= now <= "00:40":
            new_times = generate_school_times(school_type)
            if new_times:
                start_time, end_time, bedtime = new_times
                logging.info(f"Daily times regenerated → Start: {start_time}, End: {end_time}, Bed: {bedtime}")
            time.sleep(60 * 10)  # Sleep for 10 minutes to avoid immediate re-generation

        # Check if current time is near any of the scheduled interaction points
        if any(is_within_time(now, t) for t in [start_time, end_time, bedtime]):
            # Prevent rapid re-activation within a short period (e.g., 15 minutes)
            if not last_activation or (datetime.now() - last_activation) > timedelta(minutes=15):
                logging.info(f"Scheduled session triggered at {now}")
                last_activation = datetime.now()

                # Determine session duration based on the triggered time
                duration: int = {
                    start_time: random.randint(45, 60),    # Morning session
                    end_time: random.randint(160, 180),    # Afternoon/Evening session
                    bedtime: random.randint(75, 90)        # Bedtime session
                }.get(now, 60)  # Default to 60 minutes if 'now' doesn't precisely match a scheduled time

                # Start the interaction session in a new thread to keep the scheduler responsive
                threading.Thread(target=run_session, args=(duration, pin_code, unlock_method)).start()

        time.sleep(60)  # Check every minute

# === GUI FUNCTIONS === #
def start_script() -> None:
    """
    Initiates the main script execution, launching Scrcpy and starting the scheduler
    and ADB keep-alive threads.
    """
    global scheduler_thread, adb_process

    pin_code: str = pin_entry.get()
    school_type: str = school_type_var.get()
    unlock_method: str = unlock_method_var.get()

    # Input validation
    if unlock_method == "pin" and not pin_code:
        messagebox.showwarning("Input Error", "Please enter a PIN code or select 'No PIN' for unlocking.")
        return

    if not school_type:
        messagebox.showwarning("Input Error", "Please select a school type before starting.")
        return

    if running_event.is_set():
        messagebox.showinfo("Info", "The script is already running.")
        return

    # Set running flag and update GUI state
    running_event.set()
    status_label.config(text="Status: Running...", foreground="green")
    start_button.config(state=tk.DISABLED)
    stop_button.config(state=tk.NORMAL)

    # Launch Scrcpy subprocess
    try:
        logging.info("Launching Scrcpy...")
        adb_process = subprocess.Popen(['scrcpy', '--window-title', SCRCPY_WINDOW_TITLE, '--max-size', '800', '--window-x', '0', '--window-y', '0'])
        time.sleep(2)  # Give Scrcpy a moment to initialize
        if not get_scrcpy_window():
            messagebox.showerror("Error", "Failed to launch Scrcpy or find its window. "
                                           "Ensure Scrcpy is installed and ADB is properly configured.")
            stop_script() # Attempt to clean up if Scrcpy fails to launch
            return
    except FileNotFoundError:
        messagebox.showerror("Error", "Scrcpy executable not found. Please ensure Scrcpy is installed and in your system's PATH.")
        stop_script()
        return
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred while launching Scrcpy: {e}")
        stop_script()
        return

    # Start the scheduler and ADB keep-alive threads
    scheduler_thread = threading.Thread(target=scheduler_loop, args=(school_type, pin_code, unlock_method))
    scheduler_thread.daemon = True  # Allows the main program to exit even if this thread is still running
    scheduler_thread.start()

    adb_keep_alive_thread = threading.Thread(target=keep_adb_alive)
    adb_keep_alive_thread.daemon = True
    adb_keep_alive_thread.start()

    logging.info("Script started successfully. Monitoring for scheduled interactions.")

def stop_script() -> None:
    """
    Halts the main script execution, terminating active threads and the Scrcpy process.
    """
    global scheduler_thread, adb_process

    if not running_event.is_set():
        messagebox.showinfo("Info", "The script is not currently running.")
        return

    # Clear running flag and update GUI state
    running_event.clear()
    status_label.config(text="Status: Stopped", foreground="red")
    start_button.config(state=tk.NORMAL)
    stop_button.config(state=tk.DISABLED)

    # Attempt to gracefully join the scheduler thread
    if scheduler_thread and scheduler_thread.is_alive():
        logging.info("Attempting to stop scheduler thread...")
        scheduler_thread.join(timeout=5)  # Give the thread a few seconds to finish its current task
        if scheduler_thread.is_alive():
            logging.warning("Scheduler thread did not terminate gracefully within timeout.")

    # Terminate the Scrcpy process if it's still running
    if adb_process and adb_process.poll() is None:
        logging.info("Terminating Scrcpy process...")
        adb_process.terminate()
        adb_process.wait(timeout=5)  # Wait for Scrcpy to terminate
        if adb_process.poll() is None:
            logging.warning("Scrcpy process did not terminate gracefully within timeout. Killing it.")
            adb_process.kill() # Force kill if it doesn't terminate
        logging.info("Scrcpy process terminated.")
    
    logging.info("Script stopped.")

# === GUI SETUP === #
root = tk.Tk()
root.title("IFDL Instagram Automation")
root.geometry("400x350")
root.resizable(False, False) # Prevent window resizing

# Configure consistent styling for Tkinter widgets
style = ttk.Style()
style.theme_use('clam')  # A modern-looking theme
style.configure('TFrame', background='#e0e0e0')
style.configure('TLabel', background='#e0e0e0', font=('Arial', 10))
style.configure('TButton', font=('Arial', 10, 'bold'), padding=5)
style.configure('TRadiobutton', background='#e0e0e0', font=('Arial', 10))

# Main frame for padding and layout
main_frame = ttk.Frame(root, padding="20")
main_frame.pack(fill=tk.BOTH, expand=True)

# Phone Unlock Method section
pin_frame = ttk.LabelFrame(main_frame, text="Phone Unlock Method", padding="10")
pin_frame.pack(pady=10, fill=tk.X)

unlock_method_var = tk.StringVar(value="pin")  # Default selection to 'Use PIN'
pin_radio = ttk.Radiobutton(pin_frame, text="Use PIN", variable=unlock_method_var, value="pin")
pin_radio.pack(anchor=tk.W, pady=2)

pin_label = ttk.Label(pin_frame, text="PIN Code:")
pin_label.pack(anchor=tk.W, padx=20)
pin_entry = ttk.Entry(pin_frame, width=30, show="*")  # Mask input for PIN security
pin_entry.pack(anchor=tk.W, padx=20)

no_pin_radio = ttk.Radiobutton(pin_frame, text="No PIN (Swipe to Unlock)", variable=unlock_method_var, value="no_pin")
no_pin_radio.pack(anchor=tk.W, pady=2)

# School Type Selection section
school_frame = ttk.LabelFrame(main_frame, text="School Type", padding="10")
school_frame.pack(pady=10, fill=tk.X)

school_type_var = tk.StringVar() # Variable to hold the selected school type
ttk.Radiobutton(school_frame, text="University (u)", variable=school_type_var, value="u").pack(anchor=tk.W)
ttk.Radiobutton(school_frame, text="High School (h)", variable=school_type_var, value="h").pack(anchor=tk.W)
ttk.Radiobutton(school_frame, text="Primary School (p)", variable=school_type_var, value="p").pack(anchor=tk.W)

# Control Buttons section
button_frame = ttk.Frame(main_frame)
button_frame.pack(pady=15)

start_button = ttk.Button(button_frame, text="Start Script", command=start_script)
start_button.pack(side=tk.LEFT, padx=5)

stop_button = ttk.Button(button_frame, text="Stop Script", command=stop_script, state=tk.DISABLED)
stop_button.pack(side=tk.LEFT, padx=5)

# Status Label to provide user feedback
status_label = ttk.Label(main_frame, text="Status: Idle", foreground="blue")
status_label.pack(pady=10)

# === MAIN ENTRY POINT === #
if __name__ == "__main__":
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logging.info("GUI closed by user (KeyboardInterrupt).")
    finally:
        # Ensure cleanup happens if the GUI window is closed directly
        if running_event.is_set():
            logging.info("GUI closed while script was running. Attempting to stop script cleanly.")
            stop_script()
