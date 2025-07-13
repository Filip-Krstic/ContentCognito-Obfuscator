# ContentCognito-Obfuscator

**Description:** ContentCognito-Obfuscator: A research-oriented tool for social media privacy. This script simulates human-like Instagram activity on Android (ADB/Scrcpy), using CLIP for content-aware interactions and diurnal patterns. It demonstrates behavioral simulation as a defense against automated profiling, contributing to digital privacy research.

---

## Overview

This repository hosts the **Instagram Fake Data Logger (IFDL.py)**, which serves as a tool for exploring concepts in digital privacy and behavioral obfuscation. Its primary purpose is to simulate human-like activity on Instagram to understand and counter automated psychological profiling attempts. By generating plausible, varied engagement, IFDL aims to reduce the accuracy of AI systems attempting to infer user traits from their online behavior.

**Important Note:** This script is developed **solely for research and educational purposes** to explore concepts in digital privacy, adversarial AI, and behavioral obfuscation. It is intended for use in controlled environments to understand the dynamics of automated profiling and its countermeasures. **Research findings utilizing this script will be published soon.**

The script operates through a user-friendly Graphical User Interface (GUI) for easy configuration. It leverages **ADB (Android Debug Bridge)** for low-level device control and **Scrcpy** for mirroring and interacting with the Android device's screen. A **CLIP (Contrastive Language-Image Pre-training) model** is employed to enable content-aware interactions, while randomized timing and diurnal patterns ensure the simulated activity is difficult to distinguish from genuine human usage.

---

## Features

* **GUI-driven Configuration:** User-friendly interface built with `tkinter` for easy setup of automation parameters.
* **Flexible Device Unlocking:**
    * Option to enter a **PIN code** for secure device unlocking.
    * Option for **"No PIN" unlock**, performing a simple swipe gesture, suitable for devices without strict lock screens.
* **Scheduled Interactions:** Automates interactions based on **diurnal patterns** tailored for:
    * **University** students
    * **High School** students
    * **Primary School** students
    This makes the activity schedule indistinguishable from organic user behavior.
* **Intelligent Content Interaction (Content-Aware):**
    * Utilizes a **CLIP model** to classify on-screen images and text against a curated list of relevant labels.
    * Performs simulated **clicks** and **likes** based on **semantic matching** (e.g., liking Reels based on detected content relevance).
    * Simulates **randomized scrolling** and **pauses** to mimic natural browsing.
* **Behavioral Obfuscation:** Generates **plausible noise** by emulating human engagement and randomizing timing and content interactions, contributing to the study of reducing profiling accuracy.
* **Persistent ADB Connection:** Maintains an active ADB connection throughout the script's runtime, ensuring continuous device control.
* **Label Tracking:** Keeps a count of detected labels, saved to a CSV file (`label_counts.csv`), providing basic insights into simulated engagement.
* **Graceful Shutdown:** Ensures clean termination of all background processes (Scrcpy, threads) upon stopping the script or closing the GUI.

---

## Prerequisites

Before running the script, ensure you have the following installed and configured:

1.  **Python 3.8+**: Download from [python.org](https://www.python.org/downloads/).
2.  **ADB (Android Debug Bridge)**:
    * Part of the Android SDK Platform-Tools.
    * Ensure `adb` is in your system's **PATH**.
    * You can download Platform-Tools from [developer.android.com](https://developer.android.com/tools/releases/platform-tools).
3.  **Scrcpy**:
    * A free and open-source application for displaying and controlling your Android device connected via USB (or wirelessly) on your computer.
    * Ensure `scrcpy` is in your system's **PATH**.
    * Download from [github.com/Genymobile/scrcpy](https://github.com/Genymobile/scrcpy).
4.  **Android Device**:
    * An Android phone or tablet with **Developer Options** and **USB Debugging** enabled.
    * **For ethical reasons, the phone must remain physically plugged into the computer via USB while the script is running.** This ensures direct user oversight and control over the automated interactions.

---

## Installation

1.  **Clone the Repository (or download the script):**
    ```bash
    git clone [https://github.com/your-username/ContentCognito-Obfuscator.git](https://github.com/your-username/ContentCognito-Obfuscator.git)
    cd ContentCognito-Obfuscator
    ```
    *(Replace `your-username` with your actual GitHub username or the repository URL)*

2.  **Install Python Dependencies:**
    It's recommended to use a **virtual environment**.
    ```bash
    python -m venv venv
    # On Windows:
    venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```
    Now, install the required Python packages:
    ```bash
    pip install pyautogui pygetwindow Pillow torch numpy transformers
    ```

3.  **Verify ADB and Scrcpy Installation:**
    Open your terminal/command prompt and run:
    ```bash
    adb devices
    ```
    You should see your connected device listed. If not, troubleshoot your ADB installation and USB debugging setup.

    Then, run:
    ```bash
    scrcpy
    ```
    This should open a mirror of your Android device's screen. Close it after verifying.

---

## Usage

1.  **Run the Script:**
    Navigate to the script's directory in your terminal (if not already there) and run:
    ```bash
    # Ensure your virtual environment is activated if you created one
    python ifdl_gui.py
    ```
    A GUI window titled "IFDL Instagram Automation" will appear.

2.  **Configure Settings in the GUI:**
    * **Phone Unlock Method:**
        * Select **"Use PIN"** and enter your phone's PIN code in the provided field. The input will be masked for security.
        * Select **"No PIN (Swipe to Unlock)"** if your device does not require a PIN/pattern for unlocking after the screen is turned on (e.g., a simple swipe is enough).
    * **School Type:**
        * Choose the relevant school type:
            * **University (u)**
            * **High School (h)**
            * **Primary School (p)**
        This selection determines the daily schedule for automated interactions.

3.  **Start the Automation:**
    Click the **"Start Script"** button.
    * The script will attempt to launch `scrcpy` and mirror your phone's screen.
    * The "Status" label will change to "Running...".
    * The script will then begin monitoring the time and performing interactions according to the chosen school type's schedule.

4.  **Stop the Automation:**
    Click the **"Stop Script"** button at any time to halt all automation processes.
    * The "Status" label will change to "Stopped".
    * All background threads and the `scrcpy` process will be terminated cleanly.

---

## How It Works (Technical Details)

The `IFDL.py` script functions by simulating human behavior through a multi-threaded approach:

1.  **Initialization:**
    * Loads the **CLIP model** (`openai/clip-vit-base-patch16`) for zero-shot image and text classification, which is crucial for content-aware interactions.
    * Determines the connected Android device's screen dimensions via ADB.
    * Launches the `scrcpy` mirror window, which serves as the visual interface for the script's interactions.

2.  **Scheduling (`scheduler_loop`):**
    * Runs in a dedicated daemon thread, continuously checking the current time against dynamically generated **diurnal patterns**. These patterns are based on average user behavior for different "school types" (University, High School, Primary School), ensuring the automated activity blends seamlessly with typical daily routines.
    * Interaction times (morning, afternoon/evening, bedtime) are randomized within specific windows and **regenerated daily** to maintain variability.
    * When the current time is within a narrow tolerance (e.g., 5 minutes) of a scheduled time, it triggers an "interaction session" in a new thread.

3.  **Interaction Session (`run_session`):**
    * Upon activation, the device is first **unlocked** using the configured method (PIN or a general swipe).
    * The session then enters a loop for a predefined duration (e.g., 45-180 minutes), designed to emulate genuine engagement periods.
    * Within the loop, `IFDL.py` generates **plausible noise** by:
        * **Content-aware Interactions:** Captures a screenshot of the `scrcpy` window. The CLIP model analyzes this image against a list of predefined `LABELS` (e.g., "love," "programming," "motogp"). If a label is detected with high confidence (e.g., > 51%), the script simulates **mouse clicks** within a randomized region of the screen. These clicks are generated using a **bounded Cauchy distribution** to introduce realistic, non-uniform randomness, making them less predictable than uniform random clicks.
        * **Randomized Engagement:** Performs **simulated vertical scroll gestures** using ADB commands. The scroll parameters (start/end coordinates, duration) are also randomized to mimic natural human scrolling.
        * **Dynamic Pauses:** The script pauses for a random duration (1-17 seconds) between actions. Longer pauses are introduced if content of interest was detected, simulating deeper engagement.
    * The counts of detected labels are persistently stored in `label_counts.csv`.
    * At the session's conclusion, the device screen is turned off.

4.  **ADB Keep-Alive (`keep_adb_alive`):**
    * A separate, lightweight background thread periodically sends a simple ADB command (`adb devices`) to the device. This critical function prevents the ADB server connection from timing out during extended periods of inactivity, ensuring continuous communication and control.

---

## Configuration

* **`LABEL_COUNT_FILE`**: `label_counts.csv`
    * This CSV file stores the cumulative counts of how many times each label (e.g., "love", "programming") has been detected by the CLIP model during automation sessions. It's created and updated automatically by the `load_label_counts` and `save_label_counts` functions.
* **`SCRCPY_WINDOW_TITLE`**: `Scrcpy_Mirror_Window`
    * This is the specific window title that the script looks for to identify and interact with the `scrcpy` mirror. If you customize the `scrcpy` window title using the `--window-title` argument, you must update this variable in the script to match.

---

## Troubleshooting

* **"ADB not found" or "Scrcpy not found" error:**
    * **Solution:** Ensure both `adb` and `scrcpy` executables are correctly installed and their respective directories are added to your system's PATH environment variable. After modifying PATH, restart your terminal or command prompt.
* **"Scrcpy window not found!" error:**
    * **Solution:** Verify that your Android device is securely connected via USB, **USB debugging** is enabled on the device, and `scrcpy` can successfully mirror your device when run manually from the terminal. Sometimes, simply restarting `scrcpy` or the Android device can resolve temporary connection issues.
* **Script starts but no interaction happens:**
    * **Check Device Connection:** Ensure your device is still connected and `adb devices` lists it.
    * **Scrcpy Window:** Make sure the Scrcpy window is open, active, and fully visible on your desktop; the script needs to screenshot it.
    * **PIN/Unlock Method:** Double-check that the correct PIN is entered or "No PIN" is selected, consistent with your device's lock screen configuration.
    * **Logging:** Review the terminal output for any `logging.error` or `logging.warning` messages, which often provide clues about underlying issues.
* **"Failed to parse screen size" error:**
    * **Solution:** This might occur if the `adb shell wm size` command returns an unexpected format from your device. While the script includes a fallback, ensure your ADB setup is standard.
* **Script crashes unexpectedly:**
    * **Dependencies:** Verify that all Python libraries are correctly installed and up-to-date. You can try reinstalling them.
    * **Resource Usage:** Running an AI model and screen mirroring can be resource-intensive. Ensure your computer has sufficient RAM and CPU to handle the workload; closing other demanding applications might help.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
