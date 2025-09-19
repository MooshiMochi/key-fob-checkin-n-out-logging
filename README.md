# Key Fob Check-In/Out Logging

## Overview

This is a Python application managed with `pip`. It allows you to track when key fobs are checked in and out. The project is designed to be easy to set up and use in any environment that supports Python.

## Setup

1. **Clone the repository:**

   ```sh
   git clone https://github.com/MooshiMochi/key-fob-checkin-n-out-logging.git
   cd key-fob-checkin-n-out-logging
   ```

2. **Create a virtual environment (recommended):**

```sh
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

3. **Install dependencies:**

   ```sh
   pip install -r requirements.txt
   ```

   if you are not on a Raspberry Pi, you may need to install the mock reader dependencies instead:

   ```sh
   pip install -r requirements-mock.txt
   ```

## Usage

1. **Run the application:**

   ```sh
   python -m app  # use the --mock flag if not on a Raspberry Pi
   ```

2. **Configuration:**

   - You need to enable SPI on your Raspberry Pi. You can do this using `raspi-config`:

     ```sh
     sudo raspi-config
     ```

     Navigate to `Interfacing Options` -> `SPI` and enable it.

## Troubleshooting

- Ensure all dependencies are installed.
- Activate your virtual environment before running commands.
- Check the terminal and Output pane for error messages.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](LICENSE)
