# EZClock

EZClock is a Telegram bot for managing employee attendance, leave requests, and daily notes.

## Features

-   **Clock-in/out:** Employees can clock in and out using a Telegram bot. The bot uses GPS to verify the employee's location.
-   **Leave requests:** Employees can request leave through the bot. Supervisors can approve or deny leave requests.
-   **Daily notes:** Employees can send notes to a designated group chat.
-   **Reporting:** Supervisors can view daily and monthly attendance statistics.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/EZClock.git
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Create a `.env` file:**
    ```bash
    cp .env.example .env
    ```
4.  **Fill in the `.env` file with your credentials:**
    -   `BOT_TOKEN`: Your Telegram bot token.
    -   `MAPS_API_KEY`: Your Google Maps API key.
    -   `WEBHOOK_URL`: Your webhook URL.
    -   `GROUP_CHAT_ID`: Your Telegram group chat ID.
5.  **Run the bot:**
    ```bash
    python main.py
    ```

## Usage

-   `/start`: Start the bot.
-   `/leave`: Request leave.
-   `/todaystat`: View today's attendance statistics (supervisors only).
-   `/monthstat`: View this month's attendance statistics (supervisors only).
-   `/msg [username] [message]`: Send a private message to an employee (supervisors only).
