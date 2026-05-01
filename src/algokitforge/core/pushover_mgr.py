import os
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv(override=True)

class PushoverManager:
    def __init__(self):
        # Support both naming conventions
        self.user_key = os.getenv("PUSHOVER_USER") or os.getenv("PUSHOVER_USER_KEY")
        self.api_token = os.getenv("PUSHOVER_TOKEN") or os.getenv("PUSHOVER_API_TOKEN")
        self.url = "https://api.pushover.net/1/messages.json"

    async def send_notification(self, message: str, title: str = "AlgoKitForge"):
        """Send a notification via Pushover."""
        if not self.user_key or not self.api_token:
            print("Pushover credentials missing. Notification not sent.")
            return False

        data = {
            "token": self.api_token,
            "user": self.user_key,
            "message": message,
            "title": title
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.url, data=data)
                response.raise_for_status()
                return True
        except Exception as e:
            print(f"Error sending Pushover notification: {e}")
            return False

# Singleton instance
pushover_mgr = PushoverManager()
